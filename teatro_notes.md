# Teatro alla Scala – RFP questionnaire (EN) – verification notes

Output: `Questionnaire_Teatro_alla_Scala_EN.docx` (18 sections, one per portal page).

## Counts

- Questions in the Word file: **767** (= codes in the portal print preview), each code once.
- DOCX translation: 702 codes; the portal print preview has 65 more, translated here from the Italian (listed below).
- Dropdown content controls: **108** = 44 with options read from the video or the DOCX + 64 seen closed in the video with options not read.
- Free-text fields: 658. One header question (GED 1981351) has no answer field in the portal.

## Method

- Video: release V1, `record.questions.pptx.mp4` (763.6 s, 10 fps). Frames extracted at scene changes (threshold 0.01, 1287 frames at full resolution) plus one frame every 30 s.
- Open lists detected by the highlight colour of the selected row (RGB 118,118,118); frames read and checked visually. Timestamps below are in video seconds.
- Closed selects detected by their border (118,118,118) and a yellow field, matched to the question title above them by OCR and fuzzy matching against the portal text. These 64 matches need checking.
- The video shows only part of the questionnaire; the other lists are text fields in the Word file unless the DOCX says 'Respond using only the list provided'.

## Dropdown lists with options read from the video (English translation)

| Code | Options | Status | Source (video t / frame) |
|---|---|---|---|
| 082GEA1240622 | 1 - Performed directly by the candidate company / 2 - Entrusted to a group company / 3 - Entrusted to a company outside the group | complete | DOCX list items; closed in video t=9-25 s |
| 082GEA1240624 | 1 - Performed directly by the candidate company / 2 - Entrusted to a group company / 3 - Entrusted to a company outside the group | complete | DOCX list items; closed in video t=15-19 s |
| 082GEA1240626 | 1 - Performed directly by the candidate company / 2 - Entrusted to a group company / 3 - Entrusted to a company outside the group | complete | DOCX list items; open list in capture Doc1.docx (portal) |
| 082GEA1240628 | 1 - Performed directly by the candidate company / 2 - Entrusted to a group company / 3 - Entrusted to a company outside the group | complete | DOCX list items; closed in video t=19-25 s |
| 082GEA1730661 | 1 - No changes to the group structure are under way or have been announced, with particular reference to the business area covered by this selection process / 2 - Changes to the group structure are under way or have been announced, with particular reference to the business area covered by this selection process | complete | DOCX answer list (portal list shown as options in translation file) |
| 082GEC1101128 | 1 - No specific style is predominantly followed / 2 - Growth management / 3 - Value management / 4 - Blended management / 5 - Other | complete | t=134.9-151.3 s (frames 251-275) |
| 082GEC1921209 | 1 - A dedicated management team for institutional clients exists / 2 - No dedicated management team for institutional clients exists | complete | t=164.7 s (frame 298) |
| 082GEC1971317 | 1 - Yes, the team will be directly involved in managing the mandate / 2 - No, the team will not be directly involved in managing the mandate | complete | t=190.8 s (frame 336) |
| 082GEC1991384 | 1 - Yes, managers have online tools to monitor the exposure to risk of the managed portfolios / 2 - No, managers do not have online tools to monitor the exposure to risk of the managed portfolios | complete | t=204.8 s (frame 352) |
| 082GEC2021414 | 1 - Yes, stop-loss mechanisms apply and will be applied to the mandate concerned / 2 - No, the management does not provide for stop-loss mechanisms | complete | t=212.1-214.7 s (frames 363, 367) |
| 082GEC2021416 | 1 - Crossing the threshold operates as a mere notification / 2 - Crossing the threshold triggers an obligation to sell | complete | t=216.5 s (frame 371) |
| 082GED1961295 | 1 - The management structure is organised by geographic areas / 2 - The management structure is organised by yield-curve segments / 3 - Other | complete | t=227.3-233.8 s (frames 386, 393) |
| 082GED2031418 | 1 - The management structure is organised by geographic areas / 2 - The management structure is organised by market segments / 3 - The management structure is organised by sectors / 4 - Other | complete | t=247.4-256.1 s (frames 426, 450) |
| 082GED2031472 | 1 - Geographic breakdown / 2 - Sector breakdown (e.g. financial vs non-financial) / 3 - Rating breakdown (e.g. High Yield) / 4 - Other | complete | t=262.5 s (frame 463) |
| 082GED2031475 | 1 - Geographic breakdown / 2 - Sector breakdown (e.g. financial vs non-financial) / 3 - Rating breakdown (e.g. High Yield) / 4 - Other | complete | t=264.8 s (frame 466) |
| 082GED2031478 | 1 - Geographic breakdown / 2 - Sector breakdown (e.g. financial vs non-financial) / 3 - Rating breakdown (e.g. High Yield) / 4 - Other | complete | t=268.2 s (frame 470) |
| 082GED2051493 | 1 - Analysis of expected growth estimates of securities / 2 - Sector analysis and sector view / 3 - Issuer fundamental analysis / 4 - Issuer risk analysis / 5 - Ability to generate cash flow / 6 - Characteristics of the issue / 7 - Manager's investment convictions / 8 - Diversification by sector / 9 - Duration of the security / 10 - Event risk / 11 - Socially responsible factors / 12 - Full replication: index membership / 13 - Liquidity / 14 - Management quality / 15 - Rating and credit risk / 16 - Relative return / 17 - Deviation between market value and theoretical value / 18 - Relative spread versus government bonds / 19 - Top-down, sector level | partial | t=272.9 s (frame 484); list scrolls, options 1-19 only visible |
| 082GEE1120515 | 1 - The management structure is organised by markets / geographic areas / 2 - The management structure is organised by sectors / 3 - Other | complete | t=297.7-309.2 s (frames 532, 557, 573) |
| 082GEE1121075 | 1 - Energy sector / 2 - Materials sector / 3 - Industrial sector / 4 - Consumer cyclical sector / 5 - Consumer non-cyclical sector / 6 - Healthcare sector / 7 - Financial sector / 8 - IT sector / 9 - Telecommunications services sector / 10 - Utilities sector | partial | t=315.6-317.1 s (frames 593, 595); list continues beyond 10 - check on portal |
| 082GEF1060495 | A system for controlling transaction costs and times is in operation (pre- and post-trade analysis) / A system for controlling transaction costs and times is in operation (pre-trade analysis only) / A system for controlling transaction costs and times is in operation (post-trade analysis only) / No system for controlling transaction costs and times is in operation | complete | t=317-322 s (frames 613-681, value shown t=349.4) |
| 082GEF1060496 | A certification of this control system by an external party is provided / An internal verification using market benchmarks to assess the quality of the activity carried out is provided / No validation process for the system is in operation | complete | t=349.4 s (frame 681) |
| 082GEF1070507 | 1 - Yes, there is a back office operating exclusively for institutional clients / 2 - No, there is no back office operating exclusively for institutional clients | complete | t=371.4 s (frame 700) |
| 082GEG1830878 | The candidate company uses an external database/research / The candidate company uses its own research / The candidate company uses both its own research and an external database/research | complete | t=429.5 s (frame 792) |
| 082GEG1840921 | 1 - The opinion of the Ethics Committee is binding on the manager / 2 - The opinion of the Ethics Committee is not binding on the manager | complete | t=420.4 s (frame 784) |
| 082GEG4994294 | Yes, uses public lists / Yes, uses the service of a provider / Yes, uses public lists and the service of a provider / No, builds the lists exclusively through its own research / No | complete | t=429.5 s (frame 792) |
| 082GEH1770731 | 1 - Yes, there have been or there are ongoing disciplinary or sanctioning measures / 2 - No, there have not been and there are no ongoing disciplinary or sanctioning measures | complete | t=466.4 s (frame 850) |
| 082GEI1780732 | 1 - A dedicated team exists for relations with institutional clients / 2 - No dedicated team exists for relations with institutional clients | complete | t=470.6 s (frame 856) |
| 082GEI1790783 | 1 - The candidate company manages investor relations directly / 2 - The candidate company entrusts investor relations to third parties | complete | t=473.9 s (frame 864) |
| 082GEI1800808 | 1 - Yes, the company undertakes to provide the above information / 2 - No, the company does not provide the above data / 3 - No, the company does not provide the above data on a daily basis but provides it less frequently | complete | t=475.1 s (frame 866) |
| 082GEI1810835 | 1 - Yes, the company undertakes to provide the above information / 2 - No, the company does not provide the above data / 3 - No, the company does not provide the above data on a daily basis but provides it less frequently | complete | t=479.7-486.6 s (frames 874-882) |
| 082GEJ1200588 | The reconciliation takes place on a daily basis, regardless of the number of transactions outstanding with the counterparty / Based on the frequency defined by regulation, according to the contracts outstanding with the counterparty | complete | t=447.1 s (frame 821) |
| 082GEJ1210578 | ISDA / EMA / Contractual terms defined by national entities (e.g. DERV Germany, FBF France, etc.) / Other contractual terms / The company does not adopt any standard contractual terms | complete | t=449.8 s (frame 826) |
| 082GEK2201672 | Directly manages the subject mandate / Delegates management to another company | complete | t=42.9-54.3 s (frames 97-104) |
| 082GEK2201716 | The delegated company belongs to the group / The delegated company does not belong to the group | complete | t=56.4-60.3 s (frames 106-107) |
| 082GEK2281736 | The activity remains with the delegating candidate company / The activity is assigned to the delegated company | complete | t=93.5 s (frame 130) |
| 082GEK2281738 | The activity remains with the delegating candidate company / The activity is assigned to the delegated company | complete | t=96.4 s (frame 133) |
| 082GEK2281739 | The activity remains with the delegating candidate company / The activity is assigned to the delegated company | complete | t=97.5 s (frame 135) |
| 082GEK2281740 | The activity remains with the delegating candidate company / The activity is assigned to the delegated company | complete | t=98.6 s (frame 137) |
| 082RFA1170530 | The benchmark used matches the one proposed in the questionnaire / The benchmark used differs from the one indicated in the questionnaire | complete | t=496.5 s (frame 905) |
| 082RFL1461114 | The benchmark used matches the one proposed in the questionnaire / The benchmark used differs from the one indicated in the questionnaire | complete | t=547.9 s (frame 1005) |
| 082RFN1501116 | The benchmark used matches the one proposed in the questionnaire / The benchmark used differs from the one indicated in the questionnaire | complete | t=577.8 s (frame 1063) |
| 082RFU1651123 | The benchmark used matches the one proposed in the questionnaire / The benchmark used differs from the one indicated in the questionnaire | complete | t=612.9 s (frame 1153) |

## Dropdowns seen in the video, options not read ('Options not visible in the video')

082GEC1941259, 082GEC1941261, 082GEC1941269, 082GEC1941292, 082GEC1941294, 082GEC1941297, 082GEC1941305, 082GEC1941308, 082GEC1941312, 082GEC1991356, 082GEC1991361, 082GEC1991371, 082GEC2021417, 082GED1981352, 082GED1981354, 082GED1981359, 082GED2051494, 082GED2051495, 082GED2071506, 082GED2071507, 082GED2071508, 082GEE1121072, 082GEE1121078, 082GEE1911230, 082GEE1911255, 082GEE1911256, 082GEE1951262, 082GEF1060500, 082GEF1060501, 082GEF1070504, 082GEJ1200582, 082GEK2281720, 082GEK2281737, 082RB13002369, 082RB13002372, 082RB13002373, 082RB13002376, 082RB13002377, 082RB13002378, 082RB13002379, 082RB13002380, 082RB13002381, 082RB13003019, 082RB13003020, 082RB13003021, 082RB13003024, 082RB13003025, 082RB13003029, 082RB13003030, 082RB13004416, 082RB13004417, 082RB13004418, 082RB13004421, 082RB13004422, 082RB13004423, 082RB13004426, 082RB13004427, 082RB13004432, 082RB13004436, 082RB13004437, 082RB13004438, 082RB13005260, 082RB13005261, 082RB13005262, 082GEA1080559, 082GEA1250635.

GEA 1080559 and 1250635 are country lists; the DOCX gives no list (GEA 1080559 has 'France' pre-filled in the translation file).

## Questions added from the portal print preview (translated from Italian)

- 082GEA2351814: GEA – Telephone number of the candidate company's contact person
- 082GED1981354: Government bonds – Selection – Second factor
- 082GED2061496: 9. Corporate High Yield security selection – Number of issuers monitored
- 082GED2061497: Corporate HY – Selection – Europe – Number of issuers
- 082GED2061498: Corporate HY – Selection – North America – Number of issuers
- 082GED2061499: Corporate HY – Selection – Market capitalisation share of monitored securities
- 082GED2061500: Corporate HY – Selection – Europe – Market capitalisation share
- 082GED2061501: Corporate HY – Selection – North America – Market capitalisation share
- 082GED2061502: Corporate HY – Number of issuers actually present in the average managed portfolio
- 082GED2061503: Corporate HY – Selection – Europe – Actual number of issuers
- 082GED2061504: Corporate HY – Selection – North America – Actual number of issuers
- 082GED2071505: 10. Corporate High Yield selection factors – Indicate in order of importance the first three factors considered in security selection
- 082GED2071506: Corporate HY – Selection – First factor
- 082GED2071507: Corporate HY – Selection – Second factor
- 082GED2071508: Corporate HY – Selection – Third factor
- 082GEK2191662: Management delegation – Specify which entity (candidate company or delegated company) completes the individual sections
- 082GEK2191663: Management delegation – The information in Section 'GEA – Candidate company – Identification information' must necessarily refer to the candidate company
- 082GEK2191664: Management delegation – This Section 'Management delegations' must be completed by the candidate company
- 082GEK2191665: Management delegation – 'GEC – Investment process' – To which company does the information contained in this section refer?
- 082GEK2191666: Management delegation – 'GEC – Investment process' – Notes
- 082GEK2191667: Management delegation – The information in Section 'GEB – Savings volumes under management' must necessarily refer to the candidate company
- 082GEK2191668: Management delegation – The information in Section 'GEH – Management of conflicts of interest' must necessarily refer to the candidate company
- 082GEK2191669: Management delegation – The information in Section 'GEI – Reporting and investor relations' must necessarily refer to the candidate company
- 082GEK2191670: Management delegation – The information in Section 'GEJ – EMIR' must necessarily refer to the candidate company
- 082GEK2191671: Management delegation – 'RFA – Asset class liquidity' – To whom do the financial results figures refer?
- 082GEK2191699: Management delegation – 'GED – Investment process, asset class: bonds' – To which company does the information contained in this section refer?
- 082GEK2191700: Management delegation – 'GEE – Investment process, asset class: equities' – To which company does the information contained in this section refer?
- 082GEK2191701: Management delegation – 'GEF – Execution of the investment process' – To which company does the information contained in this section refer?
- 082GEK2191703: Management delegation – 'GEG – Socially responsible investments' – To which company does the information contained in this section refer?
- 082GEK2191704: Management delegation – 'GED – Investment process, asset class: bonds' – Notes
- 082GEK2191705: Management delegation – 'GEE – Investment process, asset class: equities' – Notes
- 082GEK2191706: Management delegation – 'GEF – Execution of the investment process' – Notes
- 082GEK2191707: Management delegation – 'GEG – Socially responsible investments' – Notes
- 082GEK2191710: Management delegation – 'RFL – Asset class Corporate Euro bonds' – To whom do the financial results figures refer?
- 082GEK2191711: Management delegation – 'RFN – Asset class Corporate HY bonds' – To whom do the financial results figures refer?
- 082GEK2191712: Management delegation – 'RFU – Asset class Developed world equities' – To whom do the financial results figures refer?
- 082GEK2191815: Management delegation – 'RFC – Asset class Govt Euro All Maturities bonds' – To whom do the financial results figures refer?
- 082GEK2192132: Management delegation – 'RFO – Asset class Euro area equities' – To whom do the financial results figures refer?
- 082GEK2192452: Management delegation – 'RB1 – Balanced 1' – To whom do the financial results figures refer?
- 082GEK2201715: Management delegation – If the candidate company delegates the mandate to another company
- 082GEK2201716: Management delegation – State whether the delegated company belongs or does not belong to the candidate company's group
- 082GEK2201717: Management delegation – State the full corporate name of the delegated company
- 082GEK2201718: Management delegation – State the country in which the registered office of the delegated company is located
- 082GEK2201719: Management delegation – State the address of the delegated company
- 082GEK2281720: Type of management delegation – Indicate the type of delegation granted
- 082GEK2281721: Type of management delegation – Indicate the asset classes delegated
- 082GEK2281722: Type of management delegation – Government bonds Euro
- 082GEK2281723: Type of management delegation – Government bonds Europe
- 082GEK2281724: Type of management delegation – Government bonds non-Euro
- 082GEK2281725: Type of management delegation – Corporate bonds Euro
- 082GEK2281726: Type of management delegation – Corporate bonds non-Euro
- 082GEK2281727: Type of management delegation – Other bond assets. Specify which
- 082GEK2281728: Type of management delegation – Equities Euro
- 082GEK2281729: Type of management delegation – Equities Europe
- 082GEK2281730: Type of management delegation – Equities non-Euro
- 082GEK2281731: Type of management delegation – Equities USA / North America
- 082GEK2281732: Type of management delegation – Equities Japan / Pacific
- 082GEK2281733: Type of management delegation – Equities Emerging Markets
- 082GEK2281734: Type of management delegation – Other equity assets. Specify which
- 082GEK2281735: Type of management delegation – Indicate whether the following activities remain in any case with the delegating candidate company
- 082GEK2281736: Type of management delegation – Model portfolio construction, entire mandate
- 082GEK2281737: Type of management delegation – Model portfolio construction, asset classes not delegated
- 082GEK2281738: Type of management delegation – Risk management, entire portfolio
- 082GEK2281739: Type of management delegation – Risk management, asset classes not delegated
- 082GEK2281740: Type of management delegation – Reporting

## Corrections made

- The first count missed the RB1 codes (format `082RB13002392`): 83 questions were added.
- Titles given on the line before the code are taken from that line (no question shows an empty title).
