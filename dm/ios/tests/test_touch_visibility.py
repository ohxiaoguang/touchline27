"""Exercise the visibility policy used by the native touch overlay, without UIKit."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class Visibility(unittest.TestCase):
    def test_switch_controller_and_layout_combinations(self):
        header = Path(__file__).resolve().parents[1] / 'Sources/TouchControlVisibility.h'
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'check.c'
            # Expected policy states, independently enumerated: controller presence
            # dominates both visuals, while 2D retains the pad without a right visual.
            source.write_text('#include <assert.h>\n#include "' + str(header) + '"\n'
                'int main(void) { const int cases[][6] = {'
                '{0,0,0,0,0,0},{0,0,0,1,0,0},{0,0,1,0,0,0},{0,0,1,1,0,0},'
                '{0,1,0,0,0,0},{0,1,0,1,0,0},{0,1,1,0,0,0},{0,1,1,1,0,0},'
                '{1,0,0,0,1,0},{1,0,0,1,1,0},{1,0,1,0,1,0},{1,0,1,1,1,1},'
                '{1,1,0,0,0,0},{1,1,0,1,0,0},{1,1,1,0,0,0},{1,1,1,1,0,0}};'
                'for(unsigned i=0;i<sizeof cases/sizeof cases[0];i++) {'
                'const int *c=cases[i]; int pad=dm_touch_pad_visible(c[0],c[1]);'
                'assert(pad==c[4]); assert((pad&&dm_touch_right_visible(c[3],c[2]))==c[5]);'
                '} return 0; }')
            binary = Path(root) / 'check'
            subprocess.run(['clang','-Wall','-Werror',str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)

if __name__ == '__main__':
    unittest.main()
