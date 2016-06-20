#
# Simple make file to cleanup
#

clean:
	rm -f *.pyc *.log swarm/*.pyc

count:
	wc -l *.py swarm/*.py
