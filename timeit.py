import time
import sys
import subprocess

start = time.clock()
try:
	subprocess.call( sys.argv[1:] )
except WindowsError, e:
	print e

print "Execution time: %.2f seconds" % (time.clock() - start)
