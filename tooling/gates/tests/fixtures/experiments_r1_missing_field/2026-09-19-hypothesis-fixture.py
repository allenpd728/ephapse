"""Clean hypothesis-test fixture.

**Model:** pythia-70m-deduped, fp32, CPU.
**Inputs:** fixture prompt sets, defined below.
**Question:** does the fixture gate behave as specified?
**Null:** fixture null model (per-pair Poisson independence).
**Correction:** fixture correction (BH-FDR at q=0.05).
**Issue:** #11 (fixture only — not a real run).
"""

MODEL = "pythia-70m-deduped"


def main():
    print("fixture:", MODEL)


if __name__ == "__main__":
    main()
