## DEC-014 - Target model is pythia-70m-deduped; the 160M plan was unbuildable

The probed model was pythia-160m in the earlier plan, but that target is
superseded. The target model is now `pythia-70m-deduped` (`d_model=512`).
There is no Pythia-160M SAE release and no non-deduped pythia-70m release, so
the old 160M measurements were withdrawn rather than corrected.
