import builtins
import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import contextlib

from database import create_database as store
from database import process_video as pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        store.execute_sql_file(self.db, store.SCHEMA_PATH)
        store.execute_sql_file(self.db, store.ALLOWED_VALUES_PATH)
        self.db.commit()
        self.snapshot = patch.object(store, 'METADATA_PATH', self.root / 'records.json')
        self.snapshot.start()
        self.addCleanup(self.snapshot.stop)
        self.addCleanup(self.db.close)
        self.addCleanup(self.temp.cleanup)

    def prompts(self):
        return store.load_prompts(self.db,store.load_allowed_values(self.db))

    def fixture(self):
        self.prompts()
        self.db.execute("INSERT INTO generation(generation_id,prompt_id,model_name,model_version) VALUES (1,1,'test','1')")
        config = json.loads((store.ROOT_DIRECTORY / 'config/evaluation.json').read_text())
        config['quality_threshold'] = 50
        self.db.execute("INSERT INTO scoring_run VALUES (1,1,?,'{}',CURRENT_TIMESTAMP)",(json.dumps(config),))
        for i in range(1,4):
            path = self.root / f'{i}.png'
            path.write_bytes(bytes([i]))
            self.db.execute('INSERT INTO image VALUES (?,1,?,?,NULL)',(i,i,str(path)))
            self.db.execute('INSERT INTO image_score VALUES (1,?,?,80)',(i,pipeline.digest(path)))
        self.db.commit()
        return config

    def test_all_fifty_import_and_repeat(self):
        self.assertEqual(self.prompts(),50)
        self.assertEqual(self.prompts(),50)
        for table in ('prompt','subject','tattoo','scene'):
            self.assertEqual(self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0],50)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_invalid_csv_fails_before_inserting(self):
        with open(store.PROMPTS_PATH,newline='') as stream:
            reader=csv.DictReader(stream)
            rows=list(reader)
            headers=reader.fieldnames
        rows[-1]['prompt_id']=rows[0]['prompt_id']
        path=self.root/'invalid.csv'
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=headers)
            writer.writeheader(); writer.writerows(rows)
        with patch.object(store,'PROMPTS_PATH',path), self.assertRaisesRegex(ValueError,'row 51'):
            self.prompts()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM prompt').fetchone()[0],0)

    def test_resume_records_rejections_and_ratings(self):
        self.fixture()
        with patch.object(builtins,'input',side_effect=['n',KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.select_pair(self.db,1)
        self.assertEqual(self.db.execute('SELECT same_tattoo FROM image_pairs').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT status FROM review_run').fetchone()[0],'in_progress')
        with patch.object(builtins,'input',side_effect=['y','4','4','4','4','y','4','4','4','4']):
            pipeline.select_pair(self.db,1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM image_pairs').fetchone()[0],3)
        selected=self.db.execute('SELECT image_id_1,image_id_2 FROM image_pairs WHERE pair_id=(SELECT selected_pair_id FROM review_run)').fetchone()
        self.assertEqual(tuple(selected),(1,3))
        with patch.object(builtins,'input',side_effect=AssertionError('Already complete')):
            pipeline.select_pair(self.db,1)
        # Full snapshot, including circular selected-pair reference, restores cleanly.
        store.save_records(self.db)
        other=sqlite3.connect(':memory:')
        try:
            store.execute_sql_file(other,store.SCHEMA_PATH)
            store.restore_records(other)
            other.commit()
            self.assertEqual(other.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(other.execute('SELECT COUNT(*) FROM image_pairs').fetchone()[0],3)
        finally:
            other.close()

    def test_modified_image_rejected(self):
        self.fixture()
        (self.root/'1.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed since scoring'):
            pipeline.select_pair(self.db,1)

    def test_legacy_review_ids_map_to_scoring_ids(self):
        self.fixture()
        with patch.object(builtins, 'input', side_effect=['n', 'n', 'n']):
            pipeline.select_pair(self.db, 1)
        path = self.root / 'records.json'
        snapshot = json.loads(path.read_text())
        snapshot['format_version'] = 3
        for row in snapshot['tables']['review_run']:
            row['review_run_id'] = 99
        for row in snapshot['tables']['image_pairs']:
            row['review_run_id'] = 99
            del row['scoring_run_id']
        path.write_text(json.dumps(snapshot))
        other = sqlite3.connect(':memory:')
        try:
            store.execute_sql_file(other, store.SCHEMA_PATH)
            store.restore_records(other)
            other.commit()
            self.assertEqual(other.execute('SELECT DISTINCT scoring_run_id FROM image_pairs').fetchall(), [(1,)])
            self.assertNotIn('review_run_id', [row[1] for row in other.execute('PRAGMA table_info(review_run)')])
            self.assertEqual(other.execute('PRAGMA foreign_key_check').fetchall(), [])
        finally:
            other.close()

    def test_frozen_config(self):
        config=self.fixture()
        pipeline.freeze_config(self.db,config)
        config['quality_threshold']=60
        with self.assertRaisesRegex(ValueError,'frozen config'):
            pipeline.freeze_config(self.db,config)

    def test_null_threshold_rejected(self):
        with self.assertRaisesRegex(ValueError,'quality_threshold'):
            pipeline.load_config(store.ROOT_DIRECTORY/'config/evaluation.json')

    def test_cross_generation_pair_rejected(self):
        self.fixture()
        self.db.execute("INSERT INTO generation VALUES (2,1,'test','1',NULL,CURRENT_TIMESTAMP,NULL,'{}',NULL,NULL,NULL,NULL)")
        self.db.execute("INSERT INTO image VALUES (4,2,0,'other.png',NULL)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO image_pairs(generation_id,image_id_1,image_id_2,same_tattoo) VALUES (1,1,4,0)')

    def test_initialization_ignores_old_snapshot(self):
        database=self.root/'new.db'
        (self.root/'records.json').write_text('{"old":"snapshot"}')
        with patch.object(store,'DATABASE_PATH',database):
            store.create_database()
            with contextlib.closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM prompt').fetchone()[0],50)
            with self.assertRaisesRegex(ValueError,'Database exists'):
                store.create_database()

    def test_existing_snapshot_restores(self):
        database=self.root/'restored.db'
        with patch.object(store,'METADATA_PATH',store.ROOT_DIRECTORY/'data/metadata/database_records.json'):
            store.restore_records(self.db)
        self.db.commit()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM prompt').fetchone()[0],20)

    def test_migration_preserves_data_and_backup(self):
        self.fixture()
        database=self.root/'old.db'
        with contextlib.closing(sqlite3.connect(database)) as target:
            self.db.backup(target)
        with patch.object(store,'DATABASE_PATH',database):
            store.create_database('migrate')
            self.assertTrue(database.with_suffix('.db.bak').exists())
            with contextlib.closing(sqlite3.connect(database)) as migrated:
                self.assertEqual(migrated.execute('SELECT COUNT(*) FROM scoring_run').fetchone()[0],1)
                self.assertEqual(migrated.execute('PRAGMA foreign_key_check').fetchall(),[])
            with self.assertRaisesRegex(ValueError,'Backup already exists'):
                store.create_database('migrate')

    def test_extraction_rolls_back_files_and_records_on_decode_failure(self):
        self.prompts()
        self.db.execute("INSERT INTO generation(generation_id,prompt_id,model_name,model_version) VALUES (1,1,'test','1')")
        self.db.commit()
        capture=MagicMock()
        capture.isOpened.return_value=True
        capture.get.side_effect=lambda k: 1 if k==1 else 10
        capture.read.side_effect=[(True,object()),(False,None)]
        def write(path, frame):
            Path(path).write_bytes(b'frame')
            return True
        cv=SimpleNamespace(VideoCapture=lambda _:capture,CAP_PROP_FPS=1,CAP_PROP_FRAME_COUNT=2,imwrite=write)
        with patch.dict('sys.modules',{'cv2':cv}), patch.object(pipeline,'ROOT',self.root):
            with self.assertRaisesRegex(ValueError,'decoding stopped early'):
                pipeline.extract_frames(self.db,1,self.root/'video.mp4','baseline',1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM image').fetchone()[0],0)
        self.assertEqual(list(self.root.rglob('frame_*.png')),[])
        capture.release.assert_called_once()

    def test_scoring_run_persists_provenance_hashes_and_config(self):
        config=self.fixture()
        self.db.execute('DELETE FROM image_score')
        self.db.execute('DELETE FROM scoring_run')
        self.db.execute("UPDATE generation SET frame_interval=1,video_path='video.mp4',settings_json='{\"method\":\"baseline\"}'")
        self.db.commit()
        metric=MagicMock()
        metric.state_dict.return_value={}
        metric.return_value.item.return_value=80.0
        torch=SimpleNamespace(__version__='test',inference_mode=contextlib.nullcontext)
        pyiqa=SimpleNamespace(create_metric=lambda *a,**kw:metric)
        with patch.dict('sys.modules',{'torch':torch,'pyiqa':pyiqa}), patch.object(pipeline,'version',return_value='test'):
            run_id=pipeline.score_frames(self.db,1,config)
        run=self.db.execute('SELECT * FROM scoring_run WHERE scoring_run_id=?',(run_id,)).fetchone()
        self.assertEqual(json.loads(run['config_json']),config)
        self.assertEqual(len(json.loads(run['provenance_json'])['checkpoint_sha256']),64)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM image_score').fetchone()[0],3)


if __name__=='__main__':
    unittest.main()
