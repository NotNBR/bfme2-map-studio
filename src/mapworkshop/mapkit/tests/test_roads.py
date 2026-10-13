import unittest

from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create, add_object
from mapworkshop.mapkit.roads import add_segment, inspect, ANGLED, ALPHA_JOIN


class RoadTests(unittest.TestCase):
    def test_original_pair_roundtrip_preserves_modifiers_and_identity(self):
        m=create(64,64,8)
        add_segment(m,'DaleRoad01',(100,120,0),(200,250,0),name='main',
                    start_options=ANGLED,end_options=ALPHA_JOIN)
        data=m.encode(); decoded=Map(data)
        report=inspect(decoded.objects())
        self.assertEqual(report['issues'],[])
        self.assertEqual(report['pairs'][0]['flags'],[10,132])
        self.assertEqual(report['pairs'][0]['positions'],[[100,120,0],[200,250,0]])
        self.assertEqual(data,decoded.encode())
        with self.assertRaises(ValueError):
            add_segment(m,'DaleRoad01',(1,2,0),(3,4,0),name='main')

    def test_unrelated_object_cannot_be_skipped_to_find_an_end(self):
        m=create(64,64,8)
        add_segment(m,'DaleRoad01',(1,2,0),(3,4,0),name='road')
        pair=m.objects()[-2:]
        add_object(m,'GondorFighter',250,250)
        ordinary=m.objects()[-1]
        report=inspect([pair[0],ordinary,pair[1]])
        self.assertFalse(report['pairs'])
        self.assertEqual(len(report['issues']),2)
        ordinary['flags']=256
        self.assertEqual(inspect([ordinary])['uninterpreted_flags'][0]['uninterpreted_bits'],256)

    def test_rejects_invalid_authoring_without_appending_objects(self):
        m=create(64,64,8); before=m.chunk('ObjectsList').data
        for end,option in [((1,2,5),0),((float('nan'),2,0),0),((3,4,0),16),((3,4,0),256)]:
            with self.assertRaises(ValueError):
                add_segment(m,'DaleRoad01',(1,2,0),end,name='road',start_options=option)
        self.assertEqual(m.chunk('ObjectsList').data,before)


if __name__=='__main__':unittest.main()
