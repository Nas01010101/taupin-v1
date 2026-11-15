# Taupin soil-animal photo classifier (v2-dinov2s)

Triage model: it names the animal in a farmer's photo or answers "unclear: send to the lab". It is not a diagnosis; a pest call should be confirmed by a lab or an agronomist before any treatment decision.

## Model

- Architecture: `vit_small_patch14_dinov2.lvd142m` (timm), fine-tuned, 8 classes.
- File: `model/taupin.onnx`, 23.1 MB, opset 17, input `image` float32 [N,3,224,224], output `logits` [N,8].
- Operators: Add, Cast, Concat, Constant, ConstantOfShape, Conv, Div, DynamicQuantizeLinear, Equal, Erf, Expand, Gather, LayerNormalization, MatMul, MatMulInteger, Mul, Reshape, Shape, Slice, Softmax, Split, Sqrt, Squeeze, Transpose, Unsqueeze, Where.
- ONNX vs PyTorch on all val, test and OOD images: max abs logit difference 1.34e-05, top-1 agreement 100.0% (onnxruntime 1.32.0, CPU).
- The line above compares the float32 export. The shipped file has int8 MatMul weights (onnxruntime dynamic quantization, to fit 25 MB): against float32 ONNX, max abs logit difference 1.14, top-1 agreement 98.2% (lowest split). All metrics below are from the shipped int8 file.
- onnxruntime-web 1.31.1 (wasm backend, run in Node) on 24 sample images: max abs logit difference 2.64e-01 against onnxruntime CPU, max probability difference 0.045, top-1 agreement 100.0%.
- Weights: `timm/vit_small_patch14_dinov2.lvd142m` (Meta DINOv2), Apache-2.0. Self-supervised on LVD-142M, a curated set of web images.
- The sealed test split was read 7 times (`data/test_access.log`); no choice of model, epoch, temperature or threshold used it.
- Temperature 0.695 (fit on validation). Abstain below top-1 probability 0.892, chosen on validation as the lowest threshold whose answered images reach 98.0% accuracy (target met on validation: True).

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
| wireworm | 286 | 61 | 55 | 19 |
| click_beetle | 493 | 104 | 87 | 76 |
| corn_rootworm | 297 | 120 | 79 | 72 |
| white_grub | 519 | 114 | 97 | 67 |
| ground_beetle | 445 | 178 | 75 | 56 |
| millipede | 457 | 148 | 76 | 77 |
| earthworm | 522 | 92 | 83 | 33 |
| other | 833 | 159 | 204 | 91 |
| total | 3852 | 976 | 756 | 491 |

OOD sources: gbif 334, wikimedia_commons 157.

## Results

OOD (photos from other sources than the training data) is the headline number. Brackets are 95% bootstrap intervals over images (2000 resamples). Coverage is the share of photos the model answers at the abstain threshold; the rest go to "send to the lab".

| model / set | n | accuracy | macro-F1 | coverage | accuracy when answering | ECE |
|---|---|---|---|---|---|---|
| Taupin, OOD | 491 | 92.7% [90.4%, 94.9%] | 92.6% [89.9%, 94.9%] | 85.3% [n/a, n/a] | 97.4% [n/a, n/a] | 0.029 |
| CLIP zero-shot ViT-B-32/laion2b_s34b_b79k, OOD | 491 | 66.8% [62.5%, 70.9%] | 65.5% [61.3%, 69.4%] | 7.5% [5.3%, 10.0%] | 94.6% [85.7%, 100.0%] | 0.088 |
| CLIP zero-shot ViT-L-14/laion2b_s32b_b82k, OOD | 491 | 65.6% [61.5%, 69.9%] | 64.0% [59.8%, 67.9%] | 20.4% [16.9%, 23.8%] | 93.0% [87.6%, 97.7%] | 0.089 |
| CLIP zero-shot hf-hub:imageomics/bioclip/, OOD | 491 | 76.6% [72.5%, 80.2%] | 69.8% [66.5%, 73.0%] | 57.4% [53.2%, 61.7%] | 97.2% [95.0%, 98.9%] | 0.074 |
| Taupin v1-effb0 (previous), OOD | 491 | 86.2% [83.1%, 89.2%] | 84.8% [81.2%, 88.2%] | 82.1% [78.8%, 85.3%] | 93.1% [90.7%, 95.5%] | 0.027 |
| Taupin, in-distribution test | 756 | 92.5% [90.6%, 94.3%] | 93.1% [91.3%, 94.8%] | 84.9% [n/a, n/a] | 97.5% [n/a, n/a] | 0.017 |
| CLIP zero-shot ViT-B-32/laion2b_s34b_b79k, in-distribution test | 756 | 57.9% [54.2%, 61.6%] | 59.9% [56.5%, 63.1%] | 7.5% [5.7%, 9.4%] | 94.7% [88.3%, 100.0%] | 0.043 |
| CLIP zero-shot ViT-L-14/laion2b_s32b_b82k, in-distribution test | 756 | 58.9% [55.3%, 62.3%] | 61.1% [58.0%, 64.2%] | 23.9% [20.8%, 27.0%] | 92.8% [88.8%, 96.5%] | 0.086 |
| CLIP zero-shot hf-hub:imageomics/bioclip/, in-distribution test | 756 | 68.3% [64.9%, 71.6%] | 67.1% [64.2%, 69.9%] | 45.4% [41.8%, 48.9%] | 92.4% [89.5%, 95.2%] | 0.056 |
| Taupin, OOD, museum or lab specimens | 48 | 77.1% [64.6%, 87.5%] | 70.6% [51.3%, 85.6%] | 93.8% [85.4%, 100.0%] | 80.0% [67.4%, 90.9%] | 0.150 |
| CLIP zero-shot ViT-B-32/laion2b_s34b_b79k, OOD, museum or lab specimens | 48 | 60.4% [45.8%, 75.0%] | 44.7% [33.5%, 55.2%] | 4.2% [0.0%, 10.4%] | 100.0% [100.0%, 100.0%] | 0.160 |
| CLIP zero-shot ViT-L-14/laion2b_s32b_b82k, OOD, museum or lab specimens | 48 | 56.2% [41.7%, 68.8%] | 43.8% [34.8%, 53.6%] | 10.4% [4.1%, 18.8%] | 100.0% [100.0%, 100.0%] | 0.158 |
| CLIP zero-shot hf-hub:imageomics/bioclip/, OOD, museum or lab specimens | 48 | 52.1% [37.5%, 64.6%] | 38.4% [28.8%, 51.0%] | 27.1% [16.7%, 39.6%] | 92.3% [75.0%, 100.0%] | 0.170 |
| Taupin, OOD, field and other photos | 443 | 94.4% [92.3%, 96.4%] | 94.5% [91.7%, 96.6%] | 98.0% [96.6%, 99.1%] | 95.4% [93.3%, 97.3%] | 0.025 |
| CLIP zero-shot ViT-B-32/laion2b_s34b_b79k, OOD, field and other photos | 443 | 67.5% [63.0%, 71.8%] | 66.2% [61.7%, 70.3%] | 7.9% [5.4%, 10.4%] | 94.3% [85.2%, 100.0%] | 0.087 |
| CLIP zero-shot ViT-L-14/laion2b_s32b_b82k, OOD, field and other photos | 443 | 66.6% [62.3%, 71.1%] | 64.8% [60.2%, 68.9%] | 21.4% [17.6%, 25.3%] | 92.6% [87.0%, 97.7%] | 0.091 |
| CLIP zero-shot hf-hub:imageomics/bioclip/, OOD, field and other photos | 443 | 79.2% [75.4%, 82.8%] | 71.8% [68.2%, 75.4%] | 60.7% [56.2%, 65.5%] | 97.4% [95.2%, 99.2%] | 0.071 |

Abstain threshold by validation accuracy target (only the shipped target is in labels.json; coverage / accuracy when answering):

| target | threshold | val | test | OOD |
|---|---|---|---|---|
| 90.0% | 0.000 | 100.0% / 94.6% | 100.0% / 92.5% | 100.0% / 92.7% |
| 95.0% | 0.513 | 99.2% / 95.0% | 98.9% / 93.4% | 97.6% / 93.9% |
| 98.0% | 0.892 | 90.0% / 98.1% | 84.9% / 97.5% | 85.3% / 97.4% |

CLIP baselines use the same rows, a prompt ensemble per class, and their own temperature and threshold fit on the same validation split.

### Per class, OOD

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| wireworm | 81.0% | 89.5% | 85.0% | 19 |
| click_beetle | 98.7% | 98.7% | 98.7% | 76 |
| corn_rootworm | 100.0% | 87.5% | 93.3% | 72 |
| white_grub | 89.2% | 98.5% | 93.6% | 67 |
| ground_beetle | 92.7% | 91.1% | 91.9% | 56 |
| millipede | 96.0% | 93.5% | 94.7% | 77 |
| earthworm | 97.1% | 100.0% | 98.5% | 33 |
| other | 83.9% | 85.7% | 84.8% | 91 |

### Per class, in-distribution test

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| wireworm | 86.4% | 92.7% | 89.5% | 55 |
| click_beetle | 92.1% | 94.3% | 93.2% | 87 |
| corn_rootworm | 97.5% | 97.5% | 97.5% | 79 |
| white_grub | 94.8% | 93.8% | 94.3% | 97 |
| ground_beetle | 86.9% | 97.3% | 91.8% | 75 |
| millipede | 92.3% | 94.7% | 93.5% | 76 |
| earthworm | 96.4% | 97.6% | 97.0% | 83 |
| other | 92.0% | 84.3% | 88.0% | 204 |

### Confusion matrix, ood (rows true, columns predicted)

| | wireworm | click_beetle | corn_rootworm | white_grub | ground_beetle | millipede | earthworm | other |
|---|---|---|---|---|---|---|---|---|
| wireworm | 17 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| click_beetle | 0 | 75 | 0 | 0 | 1 | 0 | 0 | 0 |
| corn_rootworm | 0 | 0 | 63 | 2 | 2 | 0 | 0 | 5 |
| white_grub | 0 | 0 | 0 | 66 | 0 | 0 | 0 | 1 |
| ground_beetle | 0 | 0 | 0 | 1 | 51 | 0 | 0 | 4 |
| millipede | 0 | 0 | 0 | 0 | 0 | 72 | 1 | 4 |
| earthworm | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 0 |
| other | 4 | 0 | 0 | 5 | 1 | 3 | 0 | 78 |

### Confusion matrix, test (rows true, columns predicted)

| | wireworm | click_beetle | corn_rootworm | white_grub | ground_beetle | millipede | earthworm | other |
|---|---|---|---|---|---|---|---|---|
| wireworm | 51 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| click_beetle | 0 | 82 | 0 | 0 | 3 | 0 | 0 | 2 |
| corn_rootworm | 0 | 1 | 77 | 0 | 0 | 0 | 0 | 1 |
| white_grub | 0 | 0 | 0 | 91 | 0 | 2 | 0 | 4 |
| ground_beetle | 0 | 1 | 0 | 0 | 73 | 0 | 0 | 1 |
| millipede | 0 | 0 | 0 | 0 | 0 | 72 | 1 | 3 |
| earthworm | 0 | 0 | 0 | 1 | 0 | 1 | 81 | 0 |
| other | 8 | 5 | 2 | 4 | 8 | 3 | 2 | 172 |

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

