import tempfile
import unittest
from pathlib import Path

import app_server


class CollageTests(unittest.TestCase):
    def test_class_collage_lists_student_photos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_server.DATA = Path(tmpdir)
            student_dir = app_server.DATA / 'classes' / 'class-101' / 'people' / 'stu-001'
            student_dir.mkdir(parents=True)
            (student_dir / 'face.jpg').write_bytes(b'fake-jpg-bytes')

            collage = app_server.class_collage('class-101')

            self.assertEqual(len(collage), 1)
            self.assertEqual(collage[0]['id'], 'stu-001')
            self.assertTrue(collage[0]['photo'].endswith('/api/classes/class-101/students/stu-001/photo'))


if __name__ == '__main__':
    unittest.main()
