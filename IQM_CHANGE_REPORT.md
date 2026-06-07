# IQM Change Report — `claude/eloquent-ride-Bq8cO` vs `origin/main`

_File: `scripts/data/ingredient_quality_map.json`. Generated 2026-06-07._

This is the cumulative semantic diff of all IQM work on the branch (35 commits, "batches 1–30"). `score` is a derived field (`score = min(bio_score + 3·natural, cap)`), so the 130 `score` changes are downstream of the `bio_score` and `natural` edits below and are not re-listed.

## Summary

- Ingredients: **485 → 491** (+6 added, 0 removed)
- Parent-level field changes: **43**
- Identifier (CUI/RxCUI) changes: **230**
- Form `bio_score` changes: **50** · `natural`-flag changes: **71** · absorption-quality changes: **4**
- Forms added: **4** · aliases added: **5** · aliases removed: **18**

## A. Parents added (6) — all fungal/mushroom

**Why:** `origin/main` on this remote has no parent for these common medicinal mushrooms, so labels like "Turkey Tail Mushroom Extract" were unscorable. Added with the two-axis local-matrix model (form quality + delivery-to-site, not systemic absorption), `category_enum="herbs"`, and orthogonal fungal fields. Gradients built inversion-free.

- **`auricularia`** (Auricularia (Wood Ear)) — category_enum=`herbs`, source_origin=`fungal`, ingredient_domain=`fungal_mushroom`, local_matrix_active=`true`
    - `auricularia extract` → bio_score **9**
    - `auricularia (unspecified)` → bio_score **5**
- **`button_mushroom`** (Button Mushroom) — category_enum=`herbs`, source_origin=`fungal`, ingredient_domain=`fungal_mushroom`, local_matrix_active=`true`
    - `button mushroom extract` → bio_score **8**
    - `button mushroom (unspecified)` → bio_score **5**
- **`chaga`** (Chaga) — category_enum=`herbs`, source_origin=`fungal`, ingredient_domain=`fungal_mushroom`, local_matrix_active=`true`
    - `chaga standardized extract` → bio_score **11**
    - `chaga sclerotium` → bio_score **9**
    - `chaga (unspecified)` → bio_score **5**
- **`maitake`** (Maitake) — category_enum=`herbs`, source_origin=`fungal`, ingredient_domain=`fungal_mushroom`, local_matrix_active=`true`
    - `maitake standardized extract` → bio_score **11**
    - `maitake fruiting body` → bio_score **9**
    - `maitake (unspecified)` → bio_score **5**
- **`shiitake`** (Shiitake) — category_enum=`herbs`, source_origin=`fungal`, ingredient_domain=`fungal_mushroom`, local_matrix_active=`true`
    - `shiitake standardized extract` → bio_score **11**
    - `shiitake fruiting body` → bio_score **9**
    - `shiitake (unspecified)` → bio_score **5**
- **`turkey_tail`** (Turkey Tail) — category_enum=`herbs`, source_origin=`fungal`, ingredient_domain=`fungal_mushroom`, local_matrix_active=`true`
    - `turkey tail standardized extract` → bio_score **11**
    - `turkey tail fruiting body` → bio_score **9**
    - `turkey tail mycelium` → bio_score **7**
    - `turkey tail (unspecified)` → bio_score **5**

## B. Parent-level field changes

**Why:** (1) consolidate all mushrooms into the valid `herbs` bucket (cordyceps/cordycepsprime left `adaptogens`, ahcc left the unsafe `mushroom_extracts`); (2) add orthogonal fungal classification fields; (3) backfill 21 `null` `category_enum` from each entry's legacy `category` using only existing vocabulary; (4) normalize `fiber`→`fibers`.

| ingredient | field | main | branch |
|---|---|---|---|
| `ahcc` | category | `mushroom_extracts` | `herbs` |
| `ahcc` | category_enum | `None` | `herbs` |
| `ahcc` | source_origin | `None` | `fungal` |
| `ahcc` | ingredient_domain | `None` | `fungal_mushroom` |
| `ahcc` | local_matrix_active | `None` | `True` |
| `ahiflower_seed_oil` | category_enum | `None` | `oil` |
| `beta_caryophyllene` | category_enum | `None` | `phytonutrients` |
| `brown_kelp` | category_enum | `None` | `herbs` |
| `butterbur` | category_enum | `None` | `herbs` |
| `celadrin` | category_enum | `None` | `fatty_acids` |
| `chrysin` | category_enum | `None` | `antioxidants` |
| `common_bean_extract` | category_enum | `None` | `herbs` |
| `cordyceps` | category | `adaptogens` | `herbs` |
| `cordyceps` | category_enum | `adaptogens` | `herbs` |
| `cordyceps` | source_origin | `None` | `fungal` |
| `cordyceps` | ingredient_domain | `None` | `fungal_mushroom` |
| `cordyceps` | local_matrix_active | `None` | `True` |
| `cordycepsprime` | category | `adaptogens` | `herbs` |
| `cordycepsprime` | category_enum | `adaptogens` | `herbs` |
| `cordycepsprime` | source_origin | `None` | `fungal` |
| `cordycepsprime` | ingredient_domain | `None` | `fungal_mushroom` |
| `cordycepsprime` | local_matrix_active | `None` | `True` |
| `corn_silk` | category_enum | `None` | `herbs` |
| `evening_primrose_oil` | category_enum | `None` | `oil` |
| `fucoxanthin` | category_enum | `None` | `antioxidants` |
| `gamma_oryzanol` | category_enum | `None` | `lipid` |
| `green_lipped_mussel` | category_enum | `None` | `functional_foods` |
| `hops` | category_enum | `None` | `herbs` |
| `horsetail` | category_enum | `None` | `herbs` |
| `lactoferrin` | category_enum | `None` | `proteins` |
| `lions_mane` | source_origin | `None` | `fungal` |
| `lions_mane` | ingredient_domain | `None` | `fungal_mushroom` |
| `lions_mane` | local_matrix_active | `None` | `True` |
| `myricetin` | category_enum | `None` | `antioxidants` |
| `pgx_fiber` | category_enum | `fiber` | `fibers` |
| `phosphatidic_acid` | category_enum | `None` | `lipid` |
| `polygodial` | category_enum | `None` | `herbs` |
| `reishi` | source_origin | `None` | `fungal` |
| `reishi` | ingredient_domain | `None` | `fungal_mushroom` |
| `reishi` | local_matrix_active | `None` | `True` |
| `thyme_extract` | category_enum | `None` | `herbs` |
| `uridine_monophosphate` | category_enum | `None` | `nucleotides` |
| `white_tea` | category_enum | `None` | `herbs` |

## C. Form `bio_score` changes (50)

**Why (by theme):** absorption-axis recalibration for systemic actives (demote poorly-absorbed flavonoid/anthocyanin/carotenoid/catechin forms; fix bio_score contradicting poor-absorption notes); form-quality model for non-systemic/local actives (fibers, demulcents, mushrooms: standardized > whole/fruiting-body > unspecified); strip premium from marketing-only claims; fix unspecified-outranks-disclosed inversions.

| ingredient | form | main | branch |
|---|---|---|---|
| `apigenin` | apigenin extract | 13 | **6** |
| `astaxanthin` | natural astaxanthin (haematococcus pluvialis) | 12 | **11** |
| `astaxanthin` | synthetic astaxanthin | 12 | **10** |
| `berberine_supplement` | berberine hcl | 11 | **6** |
| `bilberry` | bilberry extract (25% anthocyanins) | 12 | **10** |
| `bioflavonoids` | citrus complex | 11 | **7** |
| `bioflavonoids` | hesperidin-rich | 12 | **8** |
| `bioflavonoids` | rutin complex | 11 | **7** |
| `bioflavonoids` | unspecified | 9 | **6** |
| `ceramides` | unspecified | 10 | **8** |
| `cordyceps` | cordyceps militaris | 13 | **11** |
| `cordyceps` | cordyceps sinensis mycelium | 9 | **8** |
| `cordycepsprime` | cordycepsprime | 12 | **10** |
| `cryptoxanthin` | beta-cryptoxanthin | 12 | **10** |
| `cyanidin_3_glucoside` | cyanidin-3-glucoside (unspecified) | 10 | **6** |
| `dha` | unspecified | 10 | **8** |
| `elderberry` | elderberry extract (sambucol) | 12 | **10** |
| `epa` | unspecified | 10 | **8** |
| `eriocitrin` | eriocitrin extract | 11 | **7** |
| `fish_oil` | unspecified | 10 | **8** |
| `flavones` | mixed flavones | 11 | **6** |
| `flavonols` | mixed flavonols | 11 | **6** |
| `fluoride` | standard | 10 | **6** |
| `glutathione_peroxidase` | glutathione peroxidase enzyme | 12 | **5** |
| `green_tea_extract` | green tea catechins | 13 | **10** |
| `hemp_seed_oil` | unspecified | 10 | **8** |
| `hyaluronic_acid` | acetylated HA | 12 | **8** |
| `hyaluronic_acid` | high molecular weight HA | 9 | **6** |
| `hyaluronic_acid` | liposomal HA | 13 | **10** |
| `hyaluronic_acid` | low molecular weight HA | 12 | **9** |
| `hyaluronic_acid` | oligosaccharide HA | 13 | **10** |
| `l_glycine` | magnesium glycinate | 15 | **14** |
| `lions_mane` | lions mane fruiting body | 11 | **9** |
| `lions_mane` | lions mane standardized extract | 15 | **11** |
| `lycopene` | lycopene extract | 13 | **10** |
| `lysozyme` | lysozyme enzyme | 10 | **5** |
| `manuka_honey` | unspecified | 10 | **8** |
| `nattokinase` | nattokinase standard | 12 | **8** |
| `nattokinase_nsk_sd` | nsk-sd | 13 | **8** |
| `organ_extracts` | freeze-dried | 12 | **9** |
| `organ_extracts` | grass-fed desiccated | 13 | **9** |
| `organ_extracts` | standard desiccated | 10 | **8** |
| `organ_extracts` | unspecified | 9 | **7** |
| `prebiotics` | human milk oligosaccharides (HMO) | 14 | **13** |
| `probiotic_unspecified` | standard | 10 | **5** |
| `reishi` | reishi standardized extract | 13 | **11** |
| `silicon` | standard | 10 | **6** |
| `slippery_elm` | standardized extract (mucilage) | 14 | **13** |
| `superoxide_dismutase` | sod supplement | 10 | **5** |
| `vitamin_a` | beta-carotene from mixed carotenoids | 12 | **10** |

## D. Form `natural`-flag changes (71)

**Why:** (1) drop the +3 natural-source bonus from ALL unspecified/generic catch-all forms (a catch-all is not a disclosed natural source); (2) fix cross-parent inconsistencies where manufactured delivery forms (liposomal/micellized/phytosome) were flagged natural; (3) correct synthetic/processed forms mislabeled natural.

| ingredient | form | main | branch |
|---|---|---|---|
| `ahcc` | AHCC (unspecified) | `True` | `False` |
| `ahiflower_seed_oil` | ahiflower seed oil (unspecified) | `True` | `False` |
| `alpha_carotene` | alpha-carotene (unspecified) | `True` | `False` |
| `arachidonic_acid` | arachidonic acid (unspecified) | `True` | `False` |
| `bacopa` | bacopa (unspecified) | `True` | `False` |
| `beta_caryophyllene` | beta-caryophyllene (unspecified) | `True` | `False` |
| `bioflavonoids` | unspecified | `True` | `False` |
| `black_cohosh` | black cohosh (unspecified) | `True` | `False` |
| `black_seed_oil` | black seed (unspecified) | `True` | `False` |
| `boswellia` | boswellia (unspecified) | `True` | `False` |
| `branched_chain_amino_acids` | standard | `True` | `False` |
| `butterbur` | butterbur (unspecified) | `True` | `False` |
| `calamari_oil` | unspecified | `True` | `False` |
| `calcium` | calcium carbonate | `True` | `False` |
| `calcium` | coral calcium | `True` | `False` |
| `ceramides` | unspecified | `True` | `False` |
| `chasteberry` | chasteberry (unspecified) | `True` | `False` |
| `chrysin` | chrysin (unspecified) | `True` | `False` |
| `citrus_bergamot` | bergamot (unspecified) | `True` | `False` |
| `cod_liver_oil` | unspecified | `True` | `False` |
| `curcumin` | curcumin (unspecified) | `True` | `False` |
| `curcumin` | liposomal curcumin | `True` | `False` |
| `cyanidin_3_glucoside` | cyanidin-3-glucoside (unspecified) | `True` | `False` |
| `dha` | unspecified | `True` | `False` |
| `epa` | unspecified | `True` | `False` |
| `evening_primrose_oil` | evening primrose oil (unspecified) | `True` | `False` |
| `fenugreek` | fenugreek (unspecified) | `True` | `False` |
| `fish_oil` | unspecified | `True` | `False` |
| `fluoride` | standard | `True` | `False` |
| `fucoxanthin` | fucoxanthin (unspecified) | `True` | `False` |
| `gamma_oryzanol` | gamma oryzanol (unspecified) | `True` | `False` |
| `glutathione` | liposomal glutathione | `True` | `False` |
| `gotu_kola` | gotu kola (unspecified) | `True` | `False` |
| `guava_leaf` | guava (unspecified) | `True` | `False` |
| `hemp_seed_oil` | unspecified | `True` | `False` |
| `hops` | hops extract (unspecified) | `True` | `False` |
| `horsetail` | horsetail extract (unspecified) | `True` | `False` |
| `inositol_hexaphosphate` | IP6 (unspecified) | `True` | `False` |
| `iodine` | iodine (unspecified) | `True` | `False` |
| `l_glycine` | magnesium glycinate | `True` | `False` |
| `lactobacillus_salivarius` | generic lactobacillus salivarius | `True` | `False` |
| `lactoferrin` | lactoferrin (unspecified) | `True` | `False` |
| `magnesium` | magnesium carbonate | `True` | `False` |
| `magnesium` | magnesium chloride | `True` | `False` |
| `magnesium` | magnesium sulfate | `True` | `False` |
| `manuka_honey` | unspecified | `True` | `False` |
| `milk_thistle` | silymarin phytosome | `True` | `False` |
| `myricetin` | myricetin (unspecified) | `True` | `False` |
| `myristic_acid` | myristic acid (unspecified) | `True` | `False` |
| `omega_3` | omega-3 (unspecified) | `True` | `False` |
| `organ_extracts` | unspecified | `True` | `False` |
| `phosphorus` | phosphate salts | `True` | `False` |
| `pine_bark_extract` | generic pine bark extract | `True` | `False` |
| `polygodial` | polygodial (unspecified) | `True` | `False` |
| `pomegranate` | pomegranate (unspecified) | `True` | `False` |
| `probiotic_unspecified` | standard | `True` | `False` |
| `saw_palmetto` | liposomal saw palmetto | `True` | `False` |
| `sea_buckthorn` | sea buckthorn (unspecified) | `True` | `False` |
| `shilajit` | shilajit (unspecified) | `True` | `False` |
| `silicon` | standard | `True` | `False` |
| `silk_amino_acids` | unspecified | `True` | `False` |
| `slippery_elm` | bark powder (unspecified) | `True` | `False` |
| `st_johns_wort` | st john's wort (unspecified) | `True` | `False` |
| `stearidonic_acid` | stearidonic acid (unspecified) | `True` | `False` |
| `taurine` | taurine (generic) | `True` | `False` |
| `tongkat_ali` | tongkat ali (unspecified) | `True` | `False` |
| `tuna_oil` | unspecified | `True` | `False` |
| `valerian` | valerian (unspecified) | `True` | `False` |
| `vitamin_d` | vitamin D2 (unspecified source) | `True` | `False` |
| `vitamin_k1` | micellized k1 | `True` | `False` |
| `white_tea` | white tea extract (unspecified) | `True` | `False` |

## E. Absorption-quality changes (4)

**Why:** fix `absorption_structured.quality` values that contradicted the form's bio_score / its peer forms (data errors).

| ingredient | form | main quality | branch quality |
|---|---|---|---|
| `fluoride` | standard | `good` | `unknown` |
| `probiotic_unspecified` | standard | `good` | `unknown` |
| `silicon` | standard | `good` | `unknown` |
| `vitamin_d` | microencapsulated D3 | `poor` | `good` |

## F. Forms added (4)

| ingredient | new form | bio_score |
|---|---|---|
| `berberine_supplement` | dihydroberberine | 11 |
| `l_theanine` | l-theanine (suntheanine / pure l-isomer) | 12 |
| `lutein` | free lutein (floraglo / lutemax, marigold) | 10 |
| `quercetin` | quercetin phytosome (quercefit) | 14 |

## G. Alias changes

**Why:** remove cross-ingredient/hijacking aliases (e.g. a generic alias pulling matches to the wrong parent) and add exact label coverage (e.g. "X Mushroom Extract" → disclosed extract form).

| ingredient | form | added | removed |
|---|---|---|---|
| `branched_chain_amino_acids` | bcaa 2:1:1 | — | amino acids, amino acids supplement, essential amino acids, essential amino acids supplement |
| `cordyceps` | cordyceps militaris | cordyceps mushroom extract | — |
| `l_theanine` | l-theanine (unspecified) | — | alphawave, suntheanine, suntheanine l-theanine |
| `lions_mane` | lions mane standardized extract | lion's mane mushroom extract, lions mane extract, lions mane mushroom extract | — |
| `lutein` | lutein (unspecified) | — | flora glo, flora-glo, floraglo, lutemax 2020, marigold extract, marigold flower extract, tagetes erecta extract |
| `quercetin` | quercetin (unspecified) | — | quercefit, quercetin phytosome |
| `reishi` | reishi standardized extract | reishi mushroom extract | — |
| `vitamin_b2_riboflavin` | riboflavin | — | colored with vitamin b2 |
| `vitamin_b9_folate` | vitamin b9 (unspecified) | — | lemon extract |

## H. Identifier (CUI/RxCUI) changes (230)

**Why:** identifier-hygiene batches — replace junk/placeholder and cross-mapped UMLS CUI / RxNorm RxCUI values with verified concepts (or explicit `null` + a `*_note` when no valid concept exists for a botanical/novel compound). These do NOT affect scoring; they affect external code/data linkage and should be spot-verified against UMLS/RxNorm.

| ingredient | field | main | branch |
|---|---|---|---|
| `5_htp` | rxcui | `258326` | `94` |
| `acetyl_l_carnitine` | rxcui | `40799` | `193` |
| `ahcc` | rxcui | `` | `None` |
| `ahiflower_seed_oil` | cui | `` | `None` |
| `ahiflower_seed_oil` | rxcui | `` | `None` |
| `allicin` | cui | `C0051140` | `C0051200` |
| `alpha_carotene` | cui | `C0052486` | `C0051336` |
| `alpha_lipoic_acid` | cui | `C0064585` | `C0023791` |
| `alpha_lipoic_acid` | rxcui | `19721` | `6417` |
| `apigenin` | cui | `C0048689` | `C0912024` |
| `ashwagandha` | cui | `C1170179` | `C0613707` |
| `ashwagandha` | rxcui | `11176` | `None` |
| `astaxanthin` | cui | `C0162316` | `C0052565` |
| `astaxanthin` | rxcui | `1165380` | `18451` |
| `beta-alanine` | cui | `C0074950` | `C0000392` |
| `beta-alanine` | rxcui | `1981` | `61` |
| `beta_caryophyllene` | rxcui | `` | `None` |
| `bilberry` | cui | `C0281934` | `C0453269` |
| `bilberry` | rxcui | `11155` | `125929` |
| `boron` | cui | `C0006057` | `C0006030` |
| `boron` | rxcui | `19718` | `1705` |
| `brown_kelp` | cui | `` | `C0022980` |
| `brown_kelp` | rxcui | `` | `None` |
| `butterbur` | rxcui | `` | `None` |
| `caffeine` | rxcui | `2103` | `1886` |
| `calcium` | rxcui | `1898` | `1895` |
| `celadrin` | cui | `` | `C5390919` |
| `celadrin` | rxcui | `` | `2380349` |
| `chlorella` | cui | `C0246281` | `C0008190` |
| `choline` | cui | `C0008489` | `C0008405` |
| `choline` | rxcui | `2079` | `None` |
| `chondroitin` | cui | `C0008494` | `C0008454` |
| `chondroitin` | rxcui | `23874` | `2473` |
| `chromium` | cui | `C0008670` | `C0008574` |
| `chromium` | rxcui | `2403` | `2496` |
| `chrysin` | rxcui | `` | `1362888` |
| `citrus_bioflavonoids` | cui | `C0595900` | `C0982043` |
| `collagen` | cui | `C0009368` | `C0009325` |
| `common_bean_extract` | cui | `` | `C4321296` |
| `common_bean_extract` | rxcui | `` | `None` |
| `copper` | cui | `C0010175` | `C0009968` |
| `copper` | rxcui | `3002` | `2837` |
| `coq10` | cui | `C0009384` | `C0041536` |
| `coq10` | rxcui | `309268` | `21406` |
| `corn_silk` | cui | `` | `C0937769` |
| `corn_silk` | rxcui | `` | `283677` |
| `cranberry` | cui | `C0678177` | `C0453273` |
| `cranberry` | rxcui | `11179` | `125933` |
| `creatine_monohydrate` | cui | `C0079823` | `C0873188` |
| `creatine_monohydrate` | rxcui | `2231` | `1310467` |
| `cryptoxanthin` | cui | `C0079171` | `C0896117` |
| `cryptoxanthin` | rxcui | `1116063` | `None` |
| `curcumin` | cui | `C0010598` | `C0010467` |
| `cyanidin_3_glucoside` | cui | `C0378245` | `C3489523` |
| `d_aspartic_acid` | cui | `C0085845` | `C0949755` |
| `d_limonene` | cui | `C0064997` | `C0064992` |
| `d_ribose` | cui | `C0035687` | `C0035549` |
| `dandelion` | cui | `C0950252` | `C0877851` |
| `dhea` | cui | `C0011083` | `C0011185` |
| `dhea` | rxcui | `3310` | `3143` |
| `digestive_enzymes` | cui | `C0017168` | `C0544420` |
| `diindolylmethane` | cui | `C0057317` | `C0163151` |
| `dmae` | cui | `C0001833` | `C0011064` |
| `dmae` | rxcui | `3351` | `3116` |
| `echinacea` | cui | `C0013599` | `C0752270` |
| `echinacea` | rxcui | `11163` | `228041` |
| `egcg` | cui | `C0059514` | `C0059438` |
| `elderberry` | cui | `C1456405` | `C1095913` |
| `ellagic_acid` | cui | `C0013894` | `C0013900` |
| `ergothioneine` | cui | `C0014700` | `C0014713` |
| `eriocitrin` | cui | `C1170498` | `C0757990` |
| `evening_primrose_oil` | cui | `` | `C0700602` |
| `evening_primrose_oil` | rxcui | `` | `203219` |
| `flavones` | cui | `C0016129` | `C0016219` |
| `flavonoids` | cui | `C0016131` | `C0596577` |
| `flavonols` | cui | `C0596577` | `C0060444` |
| `fucoxanthin` | rxcui | `` | `None` |
| `gaba` | cui | `C0016903` | `C0016904` |
| `gaba` | rxcui | `3264` | `4617` |
| `gamma_oryzanol` | rxcui | `` | `25608` |
| `garlic` | cui | `C0017076` | `C0993630` |
| `garlic` | rxcui | `12536` | `265647` |
| `ginger` | rxcui | `258322` | `285241` |
| `ginkgo` | cui | `C0017574` | `C0772125` |
| `ginkgo` | rxcui | `12522` | `236809` |
| `ginseng` | cui | `C0017579` | `C1119918` |
| `ginseng` | rxcui | `12523` | `325526` |
| `ginsenosides` | cui | `C0017686` | `C0061278` |
| `glucosamine` | cui | `C0017611` | `C0017718` |
| `glucosamine` | rxcui | `3520` | `None` |
| `glutathione` | cui | `C0018150` | `C0017817` |
| `glutathione` | rxcui | `3586` | `4890` |
| `glycyrrhizin` | cui | `C0061996` | `C0061751` |
| `grape_seed_extract` | cui | `C0246271` | `C0772454` |
| `green_lipped_mussel` | rxcui | `` | `None` |
| `green_tea_extract` | cui | `C0246278` | `C1704263` |
| `hops` | rxcui | `` | `None` |
| `horsetail` | cui | `` | `C0331746` |
| `horsetail` | rxcui | `` | `None` |
| `hyaluronic_acid` | cui | `C0010395` | `C0020196` |
| `hyaluronic_acid` | rxcui | `3498` | `5463` |
| `hyperforin` | cui | `C0250248` | `C0063217` |
| `hypericin` | cui | `C0000521` | `C0063220` |
| `inositol` | cui | `C0021641` | `C0021547` |
| `inositol` | rxcui | `5813` | `5833` |
| `iron` | cui | `C0021776` | `C0302583` |
| `isoflavones` | cui | `C0049620` | `C0022179` |
| `l_alanine` | cui | `C0001896` | `C0001898` |
| `l_alanine` | rxcui | `206` | `426` |
| `l_arginine` | cui | `C0030897` | `C0003765` |
| `l_arginine` | rxcui | `16478` | `1091` |
| `l_carnitine` | cui | `C0023118` | `C0087163` |
| `l_carnitine` | rxcui | `20279` | `None` |
| `l_citrulline` | rxcui | `2231` | `2567` |
| `l_cysteine` | cui | `C0010692` | `C0010654` |
| `l_cysteine` | rxcui | `4105` | `3024` |
| `l_glutamic_acid` | cui | `C0017792` | `C0061472` |
| `l_glutamic_acid` | rxcui | `4851` | `25916` |
| `l_glutamine` | cui | `C0017765` | `C0017797` |
| `l_glutamine` | rxcui | `4850` | `4885` |
| `l_glycine` | rxcui | `5691` | `4919` |
| `l_histidine` | rxcui | `5324` | `5340` |
| `l_isoleucine` | cui | `C0022100` | `C0022192` |
| `l_isoleucine` | rxcui | `6003` | `6033` |
| `l_leucine` | cui | `C0023492` | `C0023401` |
| `l_leucine` | rxcui | `6179` | `6308` |
| `l_lysine` | cui | `C0024228` | `C0024337` |
| `l_lysine` | rxcui | `6386` | `None` |
| `l_ornithine` | cui | `C0029235` | `C0029277` |
| `l_ornithine` | rxcui | `7834` | `314709` |
| `l_proline` | cui | `C0033306` | `C0033382` |
| `l_proline` | rxcui | `6918` | `8737` |
| `l_serine` | rxcui | `10142` | `9671` |
| `l_theanine` | cui | `C0076979` | `C0076380` |
| `l_threonine` | cui | `C0035512` | `C0040005` |
| `l_threonine` | rxcui | `6991` | `10524` |
| `l_tryptophan` | cui | `C0041081` | `C0041249` |
| `l_tryptophan` | rxcui | `7057` | `10898` |
| `l_tyrosine` | cui | `C0041408` | `C0041485` |
| `l_tyrosine` | rxcui | `7231` | `10962` |
| `l_valine` | cui | `C0042346` | `C0042285` |
| `l_valine` | rxcui | `7279` | `11115` |
| `lactoferrin` | rxcui | `` | `1425933` |
| `lycopene` | cui | `C0079196` | `C0065331` |
| `lycopene` | rxcui | `1116065` | `29008` |
| `lysozyme` | cui | `C0024245` | `C3541379` |
| `magnesium` | cui | `C0024389` | `C0024467` |
| `magnesium` | rxcui | `1312` | `6574` |
| `manganese` | cui | `C0024744` | `C0024706` |
| `manganese` | rxcui | `23003` | `6623` |
| `melatonin` | cui | `C0025195` | `C0025219` |
| `milk_thistle` | cui | `C0037536` | `C0331428` |
| `milk_thistle` | rxcui | `11188` | `259274` |
| `molybdenum` | cui | `C0026375` | `C0026402` |
| `molybdenum` | rxcui | `6676` | `7024` |
| `msm` | rxcui | `60163` | `23247` |
| `myricetin` | cui | `` | `C0067067` |
| `myricetin` | rxcui | `` | `1368374` |
| `myristic_acid` | cui | `C0369248` | `C0027138` |
| `nac` | rxcui | `3821` | `197` |
| `nattokinase` | cui | `C1138205` | `C0131956` |
| `octacosanol` | cui | `C0072695` | `C0044548` |
| `octacosanol` | rxcui | `6810` | `12166` |
| `oleuropein` | cui | `C0066503` | `C0069413` |
| `omega_3` | cui | `C0032908` | `C0015689` |
| `omega_3` | rxcui | `1004383` | `4301` |
| `paba` | rxcui | `7073` | `74` |
| `perilla_oil` | cui | `C0950252` | `C0070421` |
| `phosphatidic_acid` | rxcui | `` | `None` |
| `phosphatidylinositol` | cui | `C0031517` | `C0031621` |
| `phosphatidylserine` | cui | `C0079825` | `C0301704` |
| `phosphatidylserine` | rxcui | `8651` | `89959` |
| `phosphorus` | cui | `C0031521` | `C0031705` |
| `pine_bark_extract` | cui | `C1171396` | `C0872909` |
| `policosanol` | cui | `C0072689` | `C0215278` |
| `policosanol` | rxcui | `7508` | `69440` |
| `polygodial` | cui | `` | `C0071585` |
| `polygodial` | rxcui | `` | `None` |
| `potassium` | rxcui | `8229` | `8588` |
| `pqq` | rxcui | `1116067` | `None` |
| `prebiotics` | cui | `C1704449` | `C2717875` |
| `pregnenolone` | rxcui | `8588` | `114052` |
| `probiotics` | cui | `C1704436` | `C0525033` |
| `psyllium` | rxcui | `8640` | `8928` |
| `pygeum` | cui | `C0330996` | `C1620942` |
| `quercetin` | cui | `C0078580` | `C0034392` |
| `resveratrol` | cui | `C0074937` | `C0073096` |
| `rhodiola` | cui | `C1456394` | `C0950013` |
| `same` | rxcui | `7841` | `9504` |
| `saw_palmetto` | cui | `C0036143` | `C0771607` |
| `saw_palmetto` | rxcui | `11187` | `236344` |
| `selenium` | cui | `C0036641` | `C0036581` |
| `selenium` | rxcui | `9010` | `None` |
| `slippery_elm` | cui | `C0597235` | `C0330532` |
| `spirulina` | cui | `C0246293` | `C1095785` |
| `squalene` | cui | `C0038237` | `C0038071` |
| `stearidonic_acid` | cui | `C0075622` | `C0075197` |
| `stinging_nettle` | cui | `C0242756` | `C1618310` |
| `strontium` | rxcui | `none` | `10122` |
| `sulforaphane` | cui | `C0162315` | `C5545155` |
| `sulforaphane` | rxcui | `1116060` | `None` |
| `superoxide_dismutase` | cui | `C0039082` | `C0038838` |
| `superoxide_dismutase` | rxcui | `9822` | `10245` |
| `taurine` | cui | `C0039324` | `C0039350` |
| `taurine` | rxcui | `10335` | `10337` |
| `thyme_extract` | cui | `` | `C3541308` |
| `thyme_extract` | rxcui | `` | `1376349` |
| `tmg_betaine` | cui | `C0052827` | `C0005304` |
| `tmg_betaine` | rxcui | `35301` | `1512` |
| `turmeric` | cui | `C0209960` | `C0077524` |
| `turmeric` | rxcui | `11178` | `1114883` |
| `uridine_monophosphate` | cui | `` | `C0042002` |
| `uridine_monophosphate` | rxcui | `` | `None` |
| `vanadium` | cui | `C0042285` | `C0042306` |
| `vanadyl_sulfate` | cui | `C0042282` | `C0078023` |
| `vanadyl_sulfate` | rxcui | `11253` | `39364` |
| `vitamin_a` | rxcui | `11149` | `11246` |
| `vitamin_b12_cobalamin` | rxcui | `2626` | `11248` |
| `vitamin_b1_thiamine` | rxcui | `10405` | `10454` |
| `vitamin_b2_riboflavin` | rxcui | `9220` | `9346` |
| `vitamin_b5_pantothenic` | rxcui | `7953` | `7891` |
| `vitamin_b6_pyridoxine` | rxcui | `8807` | `None` |
| `vitamin_b7_biotin` | rxcui | `1596` | `1588` |
| `vitamin_d` | rxcui | `11148` | `11253` |
| `vitamin_e` | rxcui | `11150` | `11256` |
| `vitamin_k` | rxcui | `11151` | `11258` |
| `vitamin_k1` | rxcui | `11256` | `8308` |
| `white_tea` | rxcui | `` | `1651698` |
| `zinc` | cui | `C0043539` | `C0043481` |
| `zinc` | rxcui | `2078` | `11416` |
