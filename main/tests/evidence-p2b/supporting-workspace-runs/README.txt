Supporting runs made in the WORKSPACE while building 2B (same index.html bytes as the final build, sha256 97dd4a8b...b011; the test files had not yet been renamed to *.adapted.* and the keyboard step is the final design).
- keyboard-chooser-runs/: sections 1+9 and 2+9, three sequential runs each, single Enter press (all passed).
- mutants/: section 12 against three mutant copies (a = restoreBusy guard removed [a2.log: 2 checks FAIL, then the run was cut by its timeout, which is why a.log/a2.log have no PHASE line], b1 = sleep reset removed [10/14], b3 = epoch check removed [13/14]).
- section12-unmutated-run.log: section 12 on the unmutated build, 14/14.
- pre-extract-run/: the first complete pipeline run in the workspace (2B 189/189, ORIGINAL p1 224/225, ORIGINAL 2A 215/216, ADAPTED 2A 217/217). Preliminary; the authoritative results are the files one level up, produced from a fresh extract.
