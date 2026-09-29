import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('inventory',Path(__file__).parents[1]/'scripts/owner_inventory.py')
inventory=importlib.util.module_from_spec(spec);spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def test_reports_status_without_opening_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root/'person';config=home/'.config/workspace/config.json'
            config.parent.mkdir(parents=True)
            data=home/'data';current=data/'gmail/current';current.mkdir(parents=True)
            (current/'COMPLETE.json').write_text(json.dumps({'records':12,'bytes':42,'completed_at':'today'}))
            secret=home/'secret.json';secret.write_text('DO_NOT_INCLUDE')
            config.write_text(json.dumps({'data_root':str(data),'sources':{'gmail':{'type':'gmail','token_file':str(secret),'enabled':True}}}))
            report=inventory.collect(root)
            self.assertEqual(report[0]['sources'][0]['records'],12)
            self.assertNotIn('DO_NOT_INCLUDE',json.dumps(report))
            self.assertNotIn('secret.json',json.dumps(report))

    def test_refuses_data_root_outside_member_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'person/.config/workspace/config.json'
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({'data_root':'/etc','sources':{}}))
            self.assertTrue(inventory.collect(root)[0]['inventory_error'])
