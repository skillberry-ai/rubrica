# Locked

This file exists only to be made unreadable at test time (see
test_survey_fixture.py's exclusion-reason test): a corpus's `unreadable`
exclusion reason fires on an OSError from actually opening a file, which
committed fixture bytes cannot express on their own -- git tracks the
executable bit, not the read bit. The file otherwise reads like any other
design doc, since normally (permissions restored) it is one.
