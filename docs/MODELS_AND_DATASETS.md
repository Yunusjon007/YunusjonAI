# Ochiq modellar va ma'lumotlar bazalari / Открытые модели и базы данных / Open models and datasets

Check each license before clinical or commercial use. None of these models is a certified medical device.

## Modellar / Модели / Models

| Model | Nima beradi / Что даёт / Output | Litsenziya / License | Havola / Link | MammoAI |
|---|---|---|---|---|
| **ianpan/mammoscreen** | Rak ehtimoli + ACR zichlik A–D (CC+MLO, 1 view ham ishlaydi) / вероятность рака + плотность / cancer probability + density | Apache-2.0 | https://huggingface.co/ianpan/mammoscreen | ✅ asosiy model (`mammo_ai/models/mammoscreen.py`) |
| ianpan/mammo-crop | Ko'krak bezini kesish / кроп / breast crop | Apache-2.0 | https://huggingface.co/ianpan/mammo-crop | ✅ ixtiyoriy (`MAMMO_USE_HF_CROP=1`) |
| O'zingiz o'qitgan / Своя модель / Your own (`train/train_birads.py`) | To'g'ridan-to'g'ri BI-RADS 1–5 + zichlik | sizniki / ваша | — | ✅ `weights/birads_model.pt` |
| MONAI breast_density_classification | Zichlik A–D | see repo | https://huggingface.co/MONAI/breast_density_classification | can be added as a backend |
| Mammo-CLIP (batmanlab) | Vision-language foundation model; mass / calcification / density classifiers on VinDr | see repo | https://github.com/batmanlab/Mammo-CLIP | feature extractor for fine-tuning |
| MAM-CLIP | BI-RADS prediction from atlas-pretrained CLIP | code MIT, data CC BY-NC 4.0 | https://github.com/igulluk/MAM-CLIP | research |
| NYU breast_cancer_classifier / GMIC | Benign / malignant per breast (4 views), saliency maps | AGPL-3.0 | https://github.com/nyukat/breast_cancer_classifier , https://github.com/nyukat/GMIC | research |
| BIRADS_classifier (NYU) | BI-RADS 0/1/2 from 4 views | see repo | https://github.com/ynjiya/BIRADS_classifier | research |
| Mirai (MIT) | 1–5 year breast cancer risk | see repo | https://github.com/yala/Mirai | risk only |

## Ma'lumotlar bazalari / Базы данных / Datasets

| Dataset | Hajmi / Размер / Size | Belgilar / Разметка / Labels | Kirish / Доступ / Access |
|---|---|---|---|
| **VinDr-Mammo** | 5,000 exams, 20,000 DICOM | BI-RADS 1–5 per breast, ACR density, lesion boxes | PhysioNet (free, credentialed) https://physionet.org/content/vindr-mammo/ — `train/prepare_vindr.py` |
| **CBIS-DDSM** | ~2,600 studies (scanned film), DICOM | BI-RADS assessment, density, ROI masks, pathology | TCIA (public) https://www.cancerimagingarchive.net/collection/cbis-ddsm/ ; JPEG version (~6 GB) https://www.kaggle.com/datasets/awsaf49/cbis-ddsm-breast-cancer-image-dataset — `train/prepare_cbis_det.py` |
| INbreast | 115 cases, 410 images | BI-RADS, density, detailed contours | on request (Univ. of Porto) |
| CMMD (Chinese Mammography Database) | 1,775 patients, DICOM | benign / malignant, molecular subtype | TCIA (public) https://www.cancerimagingarchive.net/collection/cmmd/ |
| RSNA Screening Mammography | ~54,000 images | cancer, BI-RADS (partial), density | Kaggle https://www.kaggle.com/competitions/rsna-breast-cancer-detection |
| EMBED (Emory) | 3.4 M images (20% open) | BI-RADS, density, pathology | AWS on request https://registry.opendata.aws/emory-breast-imaging-dataset-embed/ |
| KAU-BCMD | ~1,400 cases, Saudi Arabia | BI-RADS 1–6 | Kaggle / Mendeley Data |
| CDD-CESM | 2,006 images, contrast-enhanced | BI-RADS, pathology, reports | TCIA (public) |
| MIAS / mini-MIAS | 322 images | abnormality class | public (old, film) |

O'z ma'lumotlaringiz ham baza: MammoAI har bir tekshiruvni `data/mammo.sqlite3` ga saqlaydi
(rasmlar `data/images/<id>/`). Biopsiya natijasini "Baza" yorlig'ida kiriting — keyin `train/calibrate.py` bilan
chegaralarni sozlaysiz yoki CSV eksport qilib modelni qayta o'qitasiz.
