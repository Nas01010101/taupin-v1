# Taupin soil-animal photo classifier (v1-effb0)

Triage model: it names the animal in a farmer's photo or answers "unclear: send to the lab". It is not a diagnosis; a pest call should be confirmed by a lab or an agronomist before any treatment decision.

## Model

- Architecture: `efficientnet_b0.ra_in1k` (timm), fine-tuned, 8 classes.
- File: `model/taupin.onnx`, 16.0 MB, opset 17, input `image` float32 [N,3,224,224], output `logits` [N,8].
- Operators: Add, Conv, Flatten, Gemm, GlobalAveragePool, Mul, ReduceMean, Sigmoid.
- ONNX vs PyTorch on all val, test and OOD images: max abs logit difference 1.79e-05, top-1 agreement 100.0% (onnxruntime 1.32.0, CPU).
- onnxruntime-web 1.31.1 (wasm backend, run in Node) on the two reference inputs: max abs logit difference 6.74e-06 against onnxruntime CPU.
- Weights: `timm/efficientnet_b0.ra_in1k`, Apache-2.0. Pretrained on ImageNet-1k, whose image terms are for non-commercial research; stated so a reuser can judge it.
- The sealed test split was read 3 times (`data/test_access.log`); no choice of model, epoch, temperature or threshold used it.
- Temperature 0.690 (fit on validation). Abstain below top-1 probability 0.738, chosen on validation as the lowest threshold whose answered images reach 95.0% accuracy (target met on validation: True).

## Classes

| id | name | pest |
|---|---|---|
| wireworm | Wireworm (click beetle larva) | yes |
| click_beetle | Click beetle (adult) | yes |
| corn_rootworm | Corn rootworm beetle (adult) | yes |
| white_grub | White grub (scarab larva) | yes |
| ground_beetle | Ground beetle (beneficial) | no |
| millipede | Millipede (not an insect) | no |
| earthworm | Earthworm (beneficial) | no |
| other | Other soil animal or object | no |

## Images per split

| class | train | val | test | ood |
|---|---|---|---|---|
| wireworm | 286 | 61 | 55 | 44 |
| click_beetle | 493 | 104 | 87 | 83 |
| corn_rootworm | 297 | 120 | 79 | 85 |
| white_grub | 519 | 114 | 97 | 79 |
| ground_beetle | 445 | 178 | 75 | 54 |
| millipede | 457 | 148 | 76 | 19 |
| earthworm | 522 | 92 | 83 | 12 |
| other | 833 | 159 | 204 | 112 |
| total | 3852 | 976 | 756 | 488 |

OOD sources: gbif 369, wikimedia_commons 119.

## Results

OOD (photos from other sources than the training data) is the headline number. Brackets are 95% bootstrap intervals over images (2000 resamples). Coverage is the share of photos the model answers at the abstain threshold; the rest go to "send to the lab".

| model / set | n | accuracy | macro-F1 | coverage | accuracy when answering | ECE |
|---|---|---|---|---|---|---|
| Taupin, OOD | 488 | 74.6% [70.5%, 78.5%] | 72.5% [67.5%, 76.7%] | 73.0% [69.1%, 76.8%] | 86.2% [82.4%, 89.8%] | 0.086 |
| CLIP zero-shot ViT-B-32/laion2b_s34b_b79k, OOD | 488 | 59.0% [54.9%, 63.3%] | 59.4% [54.3%, 63.8%] | 6.6% [4.5%, 8.8%] | 81.2% [66.7%, 94.1%] | 0.066 |
| Taupin, in-distribution test | 756 | 86.1% [83.6%, 88.6%] | 87.2% [84.8%, 89.5%] | 81.1% [78.3%, 83.9%] | 94.0% [92.1%, 95.8%] | 0.024 |
| CLIP zero-shot ViT-B-32/laion2b_s34b_b79k, in-distribution test | 756 | 57.9% [54.2%, 61.6%] | 59.9% [56.5%, 63.1%] | 7.5% [5.7%, 9.4%] | 94.7% [88.3%, 100.0%] | 0.043 |

CLIP baselines use the same rows, a prompt ensemble per class, and their own temperature and threshold fit on the same validation split.

### Per class, OOD

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| wireworm | 46.9% | 34.1% | 39.5% | 44 |
| click_beetle | 72.3% | 88.0% | 79.3% | 83 |
| corn_rootworm | 91.0% | 71.8% | 80.3% | 85 |
| white_grub | 85.3% | 81.0% | 83.1% | 79 |
| ground_beetle | 89.6% | 79.6% | 84.3% | 54 |
| millipede | 57.1% | 84.2% | 68.1% | 19 |
| earthworm | 64.7% | 91.7% | 75.9% | 12 |
| other | 67.5% | 72.3% | 69.8% | 112 |

### Per class, in-distribution test

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| wireworm | 78.3% | 85.5% | 81.7% | 55 |
| click_beetle | 79.4% | 93.1% | 85.7% | 87 |
| corn_rootworm | 91.4% | 93.7% | 92.5% | 79 |
| white_grub | 95.8% | 94.8% | 95.3% | 97 |
| ground_beetle | 79.5% | 88.0% | 83.5% | 75 |
| millipede | 89.3% | 88.2% | 88.7% | 76 |
| earthworm | 89.0% | 97.6% | 93.1% | 83 |
| other | 85.1% | 70.1% | 76.9% | 204 |

### Confusion matrix, ood (rows true, columns predicted)

| | wireworm | click_beetle | corn_rootworm | white_grub | ground_beetle | millipede | earthworm | other |
|---|---|---|---|---|---|---|---|---|
| wireworm | 15 | 19 | 1 | 0 | 1 | 1 | 1 | 6 |
| click_beetle | 0 | 73 | 3 | 0 | 2 | 0 | 0 | 5 |
| corn_rootworm | 3 | 2 | 61 | 2 | 1 | 5 | 1 | 10 |
| white_grub | 3 | 0 | 1 | 64 | 0 | 1 | 1 | 9 |
| ground_beetle | 0 | 4 | 0 | 1 | 43 | 0 | 0 | 6 |
| millipede | 0 | 0 | 1 | 0 | 0 | 16 | 0 | 2 |
| earthworm | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 1 |
| other | 11 | 3 | 0 | 8 | 1 | 5 | 3 | 81 |

### Confusion matrix, test (rows true, columns predicted)

| | wireworm | click_beetle | corn_rootworm | white_grub | ground_beetle | millipede | earthworm | other |
|---|---|---|---|---|---|---|---|---|
| wireworm | 47 | 0 | 0 | 0 | 0 | 0 | 1 | 7 |
| click_beetle | 0 | 81 | 0 | 0 | 2 | 0 | 0 | 4 |
| corn_rootworm | 0 | 2 | 74 | 0 | 0 | 0 | 0 | 3 |
| white_grub | 0 | 0 | 0 | 92 | 1 | 1 | 0 | 3 |
| ground_beetle | 0 | 4 | 3 | 0 | 66 | 0 | 0 | 2 |
| millipede | 0 | 0 | 1 | 0 | 0 | 67 | 2 | 6 |
| earthworm | 0 | 0 | 0 | 0 | 0 | 2 | 81 | 0 |
| other | 13 | 15 | 3 | 4 | 14 | 5 | 7 | 143 |

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
  with field photos, so it is harder than phone photos from one region and easier than nothing.
  It was never used for training, model selection, temperature or threshold.
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
- Baseline weights: LAION open_clip checkpoints, MIT on their Hugging Face cards.
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
threshold was set for a stated accuracy on validation; on OOD photos the accuracy when answering
is lower, as the table shows.

