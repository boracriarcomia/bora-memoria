import sys
import unittest
import uuid


@unittest.skipUnless(sys.platform == 'win32', 'Windows kernel guard')
class SingleInstanceTest(unittest.TestCase):
    def test_second_launch_is_rejected_and_guard_is_released(self):
        from single_instance import DesktopInstance
        name = 'Local\\BoraTeste-' + uuid.uuid4().hex
        first = DesktopInstance(name)
        self.addCleanup(first.close)
        self.assertTrue(first.primary)
        second = DesktopInstance(name)
        self.addCleanup(second.close)
        self.assertFalse(second.primary)
        first.close()
        third = DesktopInstance(name)
        self.addCleanup(third.close)
        self.assertTrue(third.primary)


if __name__ == '__main__':
    unittest.main()
