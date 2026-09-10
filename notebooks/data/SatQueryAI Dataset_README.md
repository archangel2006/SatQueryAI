# SatQuery AI — Dataset

This directory contains the prepared dataset for **SatQuery AI**, an interactive Vision-Language Assistant for multimodal remote-sensing image analysis through text queries.

## Dataset Structure

```text
dataset/
├── training.csv
└── BENv2_lithuania_summer.lmdb/
    ├── data.mdb
    └── lock.mdb
```

### `training.csv`

Prepared annotation/metadata file containing:

- **185,443** matched question-answer records
- **8,363** unique satellite image patches

Important columns:

| Column | Description |
|---|---|
| `patch_id` | Identifier connecting annotations to satellite imagery |
| `input` | Question / text query |
| `output` | Expected answer |
| `type` | Task type |
| `category` | Question category |
| `split_text` | Dataset split |
| `latitude` | Patch latitude |
| `longitude` | Patch longitude |
| `country_text` | Country |
| `season` | Season |
| `climate_zone` | Climate zone |

**Important:** The CSV does not contain the satellite pixels.

### `BENv2_lithuania_summer.lmdb`

This contains the actual satellite image tensors.

The current subset contains:

- **8,775** satellite patches
- **8,363** patches matched with BigEarthNet.txt annotations
- Sentinel-1 SAR data
- Sentinel-2 multispectral data
- Lithuania summer imagery

The Sentinel-2 data contains multiple spectral bands rather than ordinary RGB photographs.

## How the Dataset Connects

The two components are joined using `patch_id`:

```text
training.csv
     |
     | patch_id
     v
LMDB
     |
     v
Sentinel-1 / Sentinel-2 image tensors
```

During training, a data loader should:

1. Read a question and answer from `training.csv`
2. Read its `patch_id`
3. Retrieve the corresponding image tensor from LMDB
4. Feed the image + question to the multimodal model
5. Train against the `output`

## Dataset Statistics

### BigEarthNet.txt

The source text dataset contains approximately:

- 9.55 million annotation rows
- 464,044 unique patches

### Prepared Subset

After matching the available imagery with BigEarthNet.txt:

- 185,443 annotation records
- 8,363 unique matched patches
- ~22 annotations per matched patch on average

Task distribution:

| Task | Records |
|---|---:|
| Binary | 65,454 |
| MCQ | 60,130 |
| Bounding Box | 51,497 |
| Captioning | 8,362 |

## Data Sources

### BigEarthNet.txt

Provides text annotations including questions, answers, captions, and related remote-sensing tasks.

Official website:

https://txt.bigearth.net/

Dataset repository:

https://huggingface.co/datasets/BIFOLD-BigEarthNetv2-0/BigEarthNet.txt

### BigEarthNet v2.0 / reBEN

The underlying satellite imagery originates from the official BigEarthNet v2.0 dataset.

Official dataset description:

https://bigearth.net/static/documents/Description_BigEarthNet_v2.pdf

### Current LMDB

The LMDB is an **unofficial community conversion/subset** of BigEarthNet v2.0/reBEN, provided in a format convenient for practical use.

Current subset:

**BigEarthNetV2-Lithuania-Summer-LMDB**

## Dataset Provenance

The dataset is a mix of official and unofficial components:

- **BigEarthNet.txt** provides the text/QA annotations.
- The **8,775-image LMDB** is an unofficial community conversion/subset of the official **BigEarthNet v2.0 (reBEN)** imagery.
- The prepared `training.csv` contains the join between the text annotations and the available image subset.

This project does **not** claim to train on the complete BigEarthNet v2.0 dataset.

## Loading in Google Colab

The prepared dataset is already stored in Google Drive.

### 1. Mount Drive

```python
from google.colab import drive

drive.mount('/content/drive')
```

### 2. Set paths

```python
DATASET_DIR = "/content/drive/MyDrive/SatQueryAI/dataset"

CSV_PATH = f"{DATASET_DIR}/training.csv"
LMDB_PATH = f"{DATASET_DIR}/BENv2_lithuania_summer.lmdb"
```

### 3. Load the CSV

```python
import pandas as pd

training_df = pd.read_csv(CSV_PATH)

print(training_df.shape)
print(training_df.head())
```

Expected shape:

```text
(185443, 11)
```

### 4. Open the LMDB

```python
import lmdb

env = lmdb.open(
    LMDB_PATH,
    readonly=True,
    lock=False,
    readahead=False,
    max_readers=126
)
```

### 5. Retrieve an Image Tensor

```python
from safetensors.numpy import load as safetensor_load

patch_id = training_df.iloc[0]["patch_id"]

with env.begin(write=False) as txn:
    raw_data = txn.get(patch_id.encode())

sample = safetensor_load(raw_data)

print(sample.keys())
```

## For Team Members

Make sure the `SatQueryAI` Google Drive folder has been shared with your Google account.

Once you have access, you **do not need to rerun the original dataset download and preprocessing pipeline**.

Start by mounting Drive and loading:

```text
training.csv
+
BENv2_lithuania_summer.lmdb
```

The `patch_id` column is the bridge between them.

## Important Notes

- Do not delete or rename `patch_id`.
- Do not move `data.mdb` outside the LMDB directory.
- Do not assume `training.csv` contains the satellite images.
- Do not unnecessarily convert the LMDB into thousands of JPG/PNG files.
- Do not claim that the prototype was trained on the complete BigEarthNet v2.0 dataset.
- The prepared dataset consists of the CSV annotations/metadata **plus** the LMDB containing the actual satellite tensors.

## Project Goal

SatQuery AI aims to enable natural-language querying of remote-sensing imagery, for example:

```text
"Is there any inland water in this image?"

"How many agricultural fields are visible?"

"What land-cover types are present?"

"Is the forest adjacent to urban areas?"
```

The intended system combines satellite imagery with natural-language queries to produce the appropriate answer.
