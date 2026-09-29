import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,os.environ.get('SCRAPE_CATALOG_CODE','/opt/scrape-catalog'))
import config
import xmlParser
from scrape_catalog.reader import Reader
from scrape_catalog.store import Store


class UTCProjectionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.media=self.root/'media';self.path=self.media/'Manual/a.mp4'
        self.path.parent.mkdir(parents=True);self.path.write_bytes(b'fixture')
        self.store=Store(self.root/'catalog',self.media);self.addCleanup(self.store.close)
        self.reader=Reader(self.store.root,self.media);self.addCleanup(self.reader.close)
        for item in [patch.object(xmlParser,'get_reader',return_value=self.reader),
                     patch.object(config,'blacklist',[*config.blacklist,'cover_image']),
                     patch('requests.get',side_effect=AssertionError('No external requests'))]:
            item.start();self.addCleanup(item.stop)
    def test_native_offset_is_projected_as_utc_day(self):
        self.store.capture({'category':'twitter','tweet_id':'1','author':{'id':'10','name':'account'},
            'date':'2024-01-02T00:30:00+09:00'},'Manual/a.mp4')
        self.assertEqual(xmlParser.XmlParser(str(self.path)).parse()['date'],'2024-01-01')
    def test_preserved_xml_offset_uses_utc_day_and_keeps_evidence(self):
        nfo=self.path.with_suffix('.nfo')
        raw=b'<movie><title>Manual</title><premiered>2024-01-02T00:30:00+09:00</premiered></movie>'
        nfo.write_bytes(raw);cid=self.store.import_nfo('Manual/a.nfo',['Manual/a.mp4'])['catalog_id'];nfo.unlink()
        self.assertEqual(xmlParser.XmlParser(str(self.path)).parse()['date'],'2024-01-01')
        self.assertEqual(self.store.db(cid).execute('SELECT raw_content FROM sidecars').fetchone()[0],raw)
    def test_date_only_keeps_its_day(self):
        nfo=self.path.with_suffix('.nfo');nfo.write_text('<movie><title>Manual</title><premiered>2024-01-02</premiered></movie>')
        self.store.import_nfo('Manual/a.nfo',['Manual/a.mp4']);nfo.unlink()
        self.assertEqual(xmlParser.XmlParser(str(self.path)).parse()['date'],'2024-01-02')

if __name__=='__main__':unittest.main()
