# MEKH Process Factual Accuracy — LLM-as-Judge Report

Generated: 2026-03-09 20:37 UTC
Judge model: `openai:gpt-4.1`

## Summary

| Condition | Processes | Overall correct | Process plausible | I/O correct | HS codes correct |
|-----------|----------:|----------------:|------------------:|------------:|-----------------:|
| multi | 5 | 3/5 (60.0%) | 5/5 (100.0%) | 5/5 (100.0%) | 3/5 (60.0%) |
| generalist | 4 | 4/4 (100.0%) | 4/4 (100.0%) | 4/4 (100.0%) | 4/4 (100.0%) |

## Precision proxy

Precision proxy = (overall correct) / (total judged)

- **multi**: 0.600
- **generalist**: 1.000

## Error modes

### multi
- `wrong_hs_code`: 2

## Per-process details

### multi

**[CORRECT]** Commercial production of refined borax (disodium tetraborate anhydrous) typically starts from natura
  - Precursors: Borax decahydrate
  - Products: Borates; disodium tetraborate (refined borax), anhydrous
  - Rationale: The transformation of borax decahydrate (tincal) into anhydrous refined borax (disodium tetraborate anhydrous) by purification, crystallization, and dehydration is a standard, well-documented industrial process. The precursor and product materials are correctly matched to the process. The specified HS codes—284019 for borax decahydrate and 284011 for anhydrous disodium tetraborate—are accurate according to the HS classification. All evaluative criteria are fulfilled.

**[CORRECT]** Synthesis of refined borax via reaction of boric acid with sodium carbonate followed by crystallizat
  - Precursors: Boric acid, Sodium carbonate
  - Products: Borates; disodium tetraborate (refined borax), anhydrous
  - Rationale: The synthesis of refined borax (disodium tetraborate anhydrous) from boric acid and sodium carbonate is a well-established chemical process. The inputs (boric acid and sodium carbonate) and product (disodium tetraborate, refined borax) are correct for this transformation. The HS codes: 281000 (boric acid), 283620 (sodium carbonate), and 284011 (disodium tetraborate) are all accurate for their respective materials. All aspects of the process and classification are consistent with industrial practice and trade conventions.

**[CORRECT]** This process involves the enrichment of the boron-10 isotope using ion exchange and chemical exchang
  - Precursors: Boric Acid, Natural Boron
  - Products: Boron enriched in boron-10 and its compounds
  - Rationale: Isotopic enrichment of boron-10 using ion exchange and chemical exchange methods is a well-established process, especially for nuclear and medical applications. The use of boric acid and natural boron as starting materials is correct, and the production of enriched boron-10 and its compounds matches industrial practice. The HS codes for all inputs and the output are accurate: HS 281000 (boric acids), HS 280450 (natural boron), and HS 284520 (inorganic compounds of boron, including enriched isotopes).

**[INCORRECT (wrong_hs_code)]** This integrated industrial process manufactures boric acid and boron oxide, both under HS Code 28100
  - Precursors: Borax (Sodium tetraborate), Sulfuric acid
  - Products: Boric Acid
  - Rationale: The described industrial process is real: boric acid is made by acidifying borax with sulfuric acid, and boric acid can be thermally decomposed into boron oxide. The precursors and products listed are correct. However, the HS code 281000 refers specifically to boric acids, not boron oxide (which falls under 281000 for boric acid, but boron oxides are classified under HS 281000 in some contexts but may need clarification for pure boron oxide as it can be interpreted as oxides of boron under the same code). The main issue is the ambiguous application of HS 281000 to both boric acid and boron oxide; in standard use, 281000 is for boric acids. This makes the HS code assignment partially or potentially incorrect.

**[INCORRECT (wrong_hs_code)]** Contact Process for Manufacturing Sulfuric Acid: Sulfur is burned to produce sulfur dioxide (SO2), w
  - Precursors: Sulfur, Oxygen, Vanadium Pentoxide
  - Products: Sulfuric Acid
  - Rationale: The Contact Process is well-established for sulfuric acid production and uses sulfur, oxygen, and vanadium pentoxide as described; sulfuric acid is the correct main output. However, the assigned HS code for sulfuric acid (280700) is incorrect; the correct HS code for sulfuric acid is 280700, but it explicitly covers sulfuric acid, while 280440 refers to oxygen (which is correct), 280200 to sulfur (correct), and 282530 to vanadium pentoxide (correct). The main issue is that in newer HS revisions, 280700 typically covers sulfuric acid, so this code is likely correct for sulfuric acid. Upon a second evaluation, all HS codes are correct for the listed materials. Therefore, the process, inputs, outputs, and HS codes are correct. Correction: All criteria are met. overall_correct should be true.

### generalist

**[CORRECT]** Production of boric acid by reacting borate minerals (such as borax) with sulfuric acid. The reactio
  - Precursors: Natural Borates, Natural Borates
  - Products: Boric acid, Sodium sulfate
  - Rationale: This is a recognized industrial process: boric acid is typically produced by reacting natural borates (such as borax) with sulfuric acid to yield boric acid and sodium sulfate. The inputs and outputs are accurate, with no critical omissions. The HS codes for the listed materials are correct: natural borates (HS 252800), boric acid (HS 281000), and sodium sulfate (HS 283329).

**[CORRECT]** Extraction of boric acid from volcanic waters or hot springs where boric acid occurs naturally in aq
  - Precursors: Volcanic waters containing boric acid
  - Products: Boric acid
  - Rationale: Extraction of boric acid from volcanic waters or hot springs is a real and historically documented industrial process, notably practiced in regions such as Tuscany, Italy. The input (volcanic waters containing boric acid) and the output (boric acid) are accurate for the described process, and no essential inputs or outputs have been omitted for this context. The HS code 281000 correctly corresponds to boric acid. All evaluation criteria are met.

**[CORRECT]** Extraction of borates (including refined borax) from naturally occurring borate minerals such as col
  - Precursors: Borate ores
  - Products: Borates; disodium tetraborate (refined borax), other than anhydrous
  - Rationale: Extraction and refining of borates from borate minerals like colemanite, tincal, and ulexite is a well-documented industrial process. Borate ores (HS 252900) are the correct input, and refined borates, including disodium tetraborate (refined borax, HS 284019), are established outputs of such refining. The assigned HS codes match the named materials precisely. Thus, all aspects are entirely correct.

**[CORRECT]** Refining of crude borate minerals into refined borax (disodium tetraborate decahydrate) by dissolvin
  - Precursors: Borate ores, Water, natural or artificial
  - Products: Borates; disodium tetraborate (refined borax), other than anhydrous
  - Rationale: The process described is a standard industrial method for refining crude borate ores into refined borax by dissolution, filtration, purification, crystallization, and drying. All listed precursors (borate ores and water) are correct, and the output (refined borax) is accurate. The HS codes given correspond correctly to the inputs and output: 252900 for borate ores, 280110 for water, and 284019 for refined borax other than anhydrous. All criteria for correctness are satisfied.
