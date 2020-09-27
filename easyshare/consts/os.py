import sys

try:
    STDIN = sys.stdin.fileno()
except:
    STDIN = 0

try:
    STDOUT = sys.stdout.fileno()
except:
    STDOUT = 1

try:
    STDERR = sys.stderr.fileno()
except:
    STDERR = 2