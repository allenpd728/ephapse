"""G-R1 failing fixture: claims the infrastructure exemption in prose, without
qualifying — it tests a hypothesis but carries only three fields.

**Model:** pythia-70m-deduped, fp32, CPU.
**Question:** does the detector recover the injected correlation?
**Issue:** #11 (fixture only).

Infrastructure file: no hypothesis under test.

The declaration above is the self-granted exemption of issue #24 hole 2. Before
the fix `_is_infra` returned True on it and excused the missing `Null` and
`Correction`; the exemption is now filename-only, so this file must be judged a
hypothesis-test and reported. It still names a question and measures an injected
correlation, so it plainly is not infrastructure.
"""

MODEL = "pythia-70m-deduped"
