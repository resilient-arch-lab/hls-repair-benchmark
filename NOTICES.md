# Third-Party Notices

This artifact depends on the following third-party works.
Their source code is **not redistributed** in this repository; it is fetched
at setup time by `setup.sh`.

---

## Chrysalis-HLS

**Repository:** https://github.com/hls-edu/Chrysalis-HLS  
**License:** Apache License 2.0  
**Used for:** Bug specifications (JSON diffs) used to construct the HLS
benchmark instances.

> Copyright (c) Chrysalis-HLS contributors  
>
> Licensed under the Apache License, Version 2.0 (the "License").  
> A copy of the License is at http://www.apache.org/licenses/LICENSE-2.0

---

## CHStone (via patmos-hls)

**Repository:** https://github.com/t-crest/patmos-hls  
**CHStone upstream:** http://www.ugh.ics.keio.ac.jp/chstone/  
**License:** Individual program copyright holders (see each benchmark
source file for its copyright notice). CHStone contains no top-level
`LICENSE` file; users should review each benchmark's individual copyright
notice before use.

**Used for:** Self-checking C programs whose `main()` functions serve as
the execution oracle. The benchmark source code is cloned from the above
repository at setup time and is **not** included in this artifact.

---

## CirFix FPGA Benchmark

**Repository:** https://github.com/hls-edu/cirfix-fpga-mut  
**License:** See repository (MIT)  
**Used for:** RTL buggy/correct Verilog pairs (CirFix subset, 31 instances)
and Assignment4V Verilog pairs (59 instances), used to build the RTL
benchmark.

---

*If you use this artifact, please also cite the original Chrysalis-HLS and
CHStone papers (see the paper's bibliography).*
