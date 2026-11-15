## Data

- Training, validation and in-distribution test: iNaturalist observations whose photo is CC0 or
  CC-BY, captive observations excluded, one photo per observation (`train/fetch_inat.py`).
  Research-grade only, except for classes where that is scarce (wireworm, corn rootworm, white
  grub, false wireworm and leatherjacket larvae in "other"): there, "needs ID" observations with at
  least one agreeing identification and no disagreement are added. Larva and adult classes use the
  iNaturalist "Life Stage" annotation.
- "other" mixes centipedes, woodlice, false wireworms (Tenebrionidae larvae), leatherjackets
  (Tipulidae larvae), cutworms and other caterpillars, other beetle larvae, rove beetles, ants,
  spiders, slugs and snails, plants and fungi.
- OOD test: GBIF occurrence images from datasets other than iNaturalist (museum collections,
  national observation portals, barcoding projects) and Wikimedia Commons files that do not cite
  iNaturalist (`train/fetch_ood.py`). Only images whose own licence is CC0, CC-BY or public domain
  are kept: an open licence on a GBIF occurrence record does not license its image, so BugGuide
  and naturgucker images (no open image licence) and CC-BY-SA images are excluded. Drawings and
  plates from Commons are dropped by filename. The OOD set mixes specimen photos taken in a lab
  with field photos. It was never used for training, model selection, temperature or threshold.
- OOD audit: all 648 OOD images were looked at on contact sheets, without model predictions, and
  157 were removed (`data/ood_audit.csv`, one reason per image): 59 images in the wireworm folder
  from Commons species categories (*Agriotes lineatus*, *A. obscurus*, *A. sputator*) that show
  adult click beetles, not larvae; 29 slide, index-card and label-only photos; 48 plates,
  drawings, collages and SEM images that the filename filter missed; and 21 photos with no
  recognisable animal (cocoons, shells, microscope close-ups, empty bins), the wrong life stage
  or several species in frame. The audit was prompted by a first OOD evaluation with low wireworm scores; the
  per-image decisions did not look at predictions. On the 157 removed images every model scores
  low: this model 41 correct (26%), BioCLIP 45 (29%), CLIP ViT-L-14 36 (23%), CLIP ViT-B-32 24
  (15%). Before the audit (648 images) this model scored 76.5% accuracy, 76.3% macro-F1 and ECE
  0.151 on OOD; BioCLIP scored 65.0%.
- Wireworm OOD has 19 images after the audit (GBIF larvae only); its per-class numbers have wide
  uncertainty.
- Cross-source duplicates: no OOD image is within 6 bits (difference hash) of an iNaturalist
  image. The 31 OOD images within 8 bits of their nearest iNaturalist image were checked by eye:
  none is the same photo or the same animal. The same specimen photographed twice, once for each
  portal, would not be caught.
- Every image has a row in `data/attribution.csv` (url, author, licence, source, source id,
  class, split). Images are not in the repository; `train/fetch_inat.py` and `train/fetch_ood.py`
  download them.

## Splits

- iNaturalist rows are split by observer: the observer id is hashed into train 70 / val 15 /
  test 15, so no photographer appears on two sides. OOD comes from other sources.
- Near-duplicates: a 64-bit difference hash marks near-identical photos; an image within 6 bits
  of an image in another split is dropped, and OOD images near any iNaturalist image are dropped.
  A photographer who posts the same animal to iNaturalist and to another portal with a different
  crop can still slip through.
- The test manifest was hashed (`data/test_seal.txt`) before any training; every read of the
  test split is logged in `data/test_access.log`.

## Licences

- Code: MIT (this repository); timm and open_clip are Apache-2.0 and MIT.
- Backbone weights: see "Model" above.
- Baseline weights: LAION open_clip checkpoints (MIT on their Hugging Face cards) and BioCLIP
  (`imageomics/bioclip`, MIT).
- Images: CC0, CC-BY or public domain only, per image, with attribution in `data/attribution.csv`.

## Preprocessing (the browser must match this)

Python reference (`train/evalutil.py`, PIL bilinear with antialiasing, EXIF orientation applied):

```python
im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
s = 224 / min(im.size); w, h = max(224, round(im.width * s)), max(224, round(im.height * s))
im = im.resize((w, h), Image.BILINEAR)
l, t = (w - 224) // 2, (h - 224) // 2; im = im.crop((l, t, l + 224, t + 224))
x = ((np.asarray(im, np.float32) / 255 - mean) / std).transpose(2, 0, 1)[None]  # [1,3,224,224]
```

Browser equivalent: draw the image on a 224 x 224 canvas scaled so the short side is 224, offset
by `-Math.floor((w - 224) / 2)`, `-Math.floor((h - 224) / 2)`, with
`ctx.imageSmoothingQuality = "high"`; read RGBA bytes, drop alpha, divide by 255, subtract `mean`,
divide by `std`, and lay out channel-first (all R, then all G, then all B). Large photos downscaled
in one canvas step without smoothing alias; the model then sees a different image than in
evaluation. `model/reference_outputs.json` holds expected logits for two sample images to test
this.

## Known failure cases

- Photos outside the classes get confident answers. Of the 157 OOD images removed by the audit
  (drawings, label-only photos, adult beetles filed as wireworms, no animal in frame), the model
  answered 92 at the shipped threshold instead of sending them to the lab (146 at the 95% target;
  `abstain_check` in `metrics.json`). The abstain path catches uncertain photos of the eight
  classes, not inputs that are not soil-animal photos.
- Abstain target: the shipped threshold is the 98% validation target, not the 95% one in the
  threshold table. The choice was made after both had been scored on test and OOD, as a product
  choice: a wrong name costs the farmer more than a lab request, and at the 95% target the model
  answered almost every photo, so the lab route did not fire. It was not tuned on those sets, but
  it was not fixed in advance either (`train/set_target.py`). The intervals for coverage and
  accuracy of answered photos are not reported for this threshold.
- Museum and lab specimens (pinned, in alcohol, on a scale bar) score lower than field photos;
  see the OOD rows by photo type.
- int8 weights: the shipped file stores MatMul weights as int8 (dynamic quantization) to fit the
  25 MB budget. Its top-1 agreement with the float model (in "Model") is measured on all val,
  test and OOD images; a photo near the boundary between two classes can flip. The int8 kernels
  also differ between processors: the same file on an Apple-silicon Mac (onnxruntime 1.32.0, CPU)
  answers 457 of the 491 OOD photos correctly against 455 on the x86 evaluation machine, with the
  same coverage.

- Lab and macro specimen photos versus phone photos in the field: much of the training data is
  close-up and centred; a phone photo of soil with a small animal in it is not.
- Small objects in frame: the centre crop keeps the middle square only, and an animal that fills
  a few percent of the photo is hard to see at 224 pixels. Ask the user to crop or zoom.
- Wireworms versus other elongated larvae: false wireworms (Tenebrionidae larvae), leatherjackets,
  cutworms, centipedes and some millipedes look alike at phone resolution. These are in "other" or
  their own class, but the wireworm class has the fewest training images.
- White grub covers all scarab larvae, pest or not (Japanese beetle, June beetles, chafers, also
  dung and compost scarabs). Corn rootworm covers adults of *Diabrotica virgifera* and
  *D. barberi* only; the spotted cucumber beetle and other *Diabrotica* are not in training.
- Several animals in one photo, eggs and pupae, damaged or dead specimens, and photos at night are
  under-represented.
- iNaturalist data is global and skewed to Europe and North America; Quebec species are a subset.

## Intended use

Triage for a farmer scouting a field: name the likely animal, flag the pest classes, and send
uncertain photos to a lab. Not for treatment decisions without confirmation. The abstain
threshold was set for a stated accuracy on validation; the results table gives the accuracy when
answering on the test and OOD sets, and the threshold table gives a stricter setting. A deployment
should check a few hundred of its own field photos before trusting either number.
