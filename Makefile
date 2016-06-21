#
# Simple make file to cleanup
#

clean:
	rm -f *.pyc *.log swarmcore/*.pyc plugins/*.pyc

count:
	wc -l *.py swarm/*.py
