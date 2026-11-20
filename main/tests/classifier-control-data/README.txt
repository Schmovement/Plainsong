REAL candidate-1 shapes used as classifier negative controls (tests/test_mutant_verdict_4.py). These are byte copies of the raw results/logs of the fresh-extract mutation run of candidate 1
(plainsong-checkpoint-p4.zip, sha256 5dbb1a49...): four mutants whose scenario ABORTED part-way (F8 and F9: R5 14 checks versus the 21 of the control; B3: R9 88 versus 127; B4: R9 36 versus 127)
yet were written with complete:true and were wrongly counted DETECTED by the first classifier. The files are historical evidence in their ORIGINAL (older, lifecycle-less) format; the controls add the lifecycle record
where they need to isolate one rule. They are never regenerated.
