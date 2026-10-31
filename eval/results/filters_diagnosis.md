# Filters diagnosis

Observed candidate pools are the exact top-30 inputs to reranking. Final ranks cover all reranked candidates; absent means not returned. Cause guesses are hypotheses. The filtered mode also enables query expansion.

## quiet museums in Lisbon in winter

Extracted filters: {"city": "Lisbon", "country": "Portugal", "season": "winter", "topic": "see"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 322e24464434a270 | Lisbon | see | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## best neighborhoods for food in Porto

Extracted filters: {"city": "Porto", "country": "Portugal", "season": null, "topic": "eat"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 152891226cdf59a7 | Porto | eat | None | yes | yes | 2 | 2 |
| f3bd6bf06adf107f | Porto | eat | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## family hotels in Madrid

Extracted filters: {"city": "Madrid", "country": "Spain", "season": null, "topic": "sleep"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| e94a1fd75936544c | Madrid | see | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## day trips from Rome by train

Extracted filters: {"city": "Rome", "country": "Italy", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 27b2ae4457b059b4 | Rome | see | None | yes | yes | 3 | 2 |
| cfc322ec869db2b0 | Rome | buy | None | yes | yes | 8 | 5 |
| 66002943b3b8f16a | Rome | see | summer | yes | yes | 5 | 3 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## affordable hostels in Amsterdam

Extracted filters: {"city": "Amsterdam", "country": "Netherlands", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 6cfd00f6cbee0345 | Amsterdam | sleep | winter | yes | no | 1 | absent |
| c13d4fb06aea16cb | Amsterdam | sleep | winter | yes | yes | 2 | 1 |

Cause guess: Query expansion/fusion or the 30-candidate cutoff likely displaced relevant candidates.

## historic walking routes in Florence

Extracted filters: {"city": "Florence", "country": "Italy", "season": null, "topic": "do"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| eb52cd1cc48239ca | Florence | see | summer | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## safe nightlife in Berlin

Extracted filters: {"city": "Berlin", "country": "Germany", "season": null, "topic": "do"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 9e4fee20bc9ce4e3 | Berlin | drink | None | yes | no | 3 | absent |
| ffe9236ed04005b1 | Berlin | stay safe | None | yes | no | 1 | absent |

Cause guess: Query expansion/fusion or the 30-candidate cutoff likely displaced relevant candidates.

## coffee culture in Vienna

Extracted filters: {"city": "Vienna", "country": "Austria", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| a717322abfd1f886 | Vienna | eat | None | yes | yes | 3 | 2 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## cheap public transport in Prague

Extracted filters: {"city": "Prague", "country": "Czechia", "season": null, "topic": "get around"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 21246473b10286ac | Prague | drink | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## best river walks in Budapest

Extracted filters: {"city": "Budapest", "country": "Hungary", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 7b3edc176b866046 | Budapest | see | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## food markets in Valencia

Extracted filters: {"city": "Valencia", "country": "Spain", "season": null, "topic": "eat"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 46d6a44c3048277b | Valencia | eat | None | yes | yes | 2 | 2 |
| 841ce87387079c85 | Valencia | see | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## sunny beaches in Seville

Extracted filters: {"city": "Seville", "country": "Spain", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 7442101535014215 | Seville | other | None | yes | yes | 20 | 21 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## best wine bars in Lyon

Extracted filters: {"city": "Lyon", "country": "France", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 88dc8646d2e8e257 | Lyon | eat | summer | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## cycling routes in Copenhagen

Extracted filters: {"city": "Copenhagen", "country": "Denmark", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 38d9a760a3144c2b | Copenhagen | do | None | yes | yes | 1 | 1 |
| 81347917f3c5b65b | Copenhagen | do | None | yes | no | 3 | absent |
| d69c98e7becb0308 | Copenhagen | see | None | no | yes | absent | 3 |

Cause guess: Query expansion/fusion or the 30-candidate cutoff likely displaced relevant candidates.

## winter markets in Stockholm

Extracted filters: {"city": "Stockholm", "country": "Sweden", "season": "winter", "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 9a3fbc62b5b023a7 | Stockholm | do | winter | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## cheap eats in Dublin

Extracted filters: {"city": "Dublin", "country": "Ireland", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 45acfe174a757143 | Dublin | eat | None | yes | yes | 3 | 3 |
| 8d6a0f1bcfb94104 | Dublin | eat | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## ancient ruins in Athens

Extracted filters: {"city": "Athens", "country": "Greece", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| a9d77836423cb740 | Athens | see | None | yes | yes | 1 | 1 |
| e76f06726bdc32a8 | Athens | see | summer | yes | yes | 4 | 4 |
| aa8daab637cc5bd7 | Athens | see | autumn | yes | yes | 2 | 2 |
| bd993f61724faf53 | Athens | see | None | yes | yes | 3 | 3 |

Cause guess: No observed difference for the labeled relevant chunks.

## local festivals in Brussels

Extracted filters: {"city": "Brussels", "country": "Belgium", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 0577dc7d6ea848e4 | Brussels | do | summer | yes | yes | 3 | 3 |

Cause guess: No observed difference for the labeled relevant chunks.

## viewpoints in Porto

Extracted filters: {"city": "Porto", "country": "Portugal", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 46f956d428b1ac24 | Porto | see | None | yes | yes | 15 | 13 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## best bakeries in Vienna

Extracted filters: {"city": "Vienna", "country": "Austria", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 88430a4c3f131b2e | Vienna | eat | None | yes | no | 1 | absent |
| a717322abfd1f886 | Vienna | eat | None | yes | yes | 4 | 1 |
| 348610f69d036479 | Vienna | eat | None | yes | no | 2 | absent |

Cause guess: Query expansion/fusion or the 30-candidate cutoff likely displaced relevant candidates.

## historic sites in Rome

Extracted filters: {"city": "Rome", "country": "Italy", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 8a6b642ec8572f11 | Rome | see | None | yes | yes | 1 | 1 |
| e7d1621e188ca9ad | Rome | do | None | yes | yes | 23 | 21 |
| 66002943b3b8f16a | Rome | see | summer | yes | yes | 5 | 5 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## night buses in Prague

Extracted filters: {"city": "Prague", "country": "Czechia", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| d8186f1cf5498d95 | Prague | do | None | yes | yes | 2 | 1 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## best museums in Amsterdam

Extracted filters: {"city": "Amsterdam", "country": "Netherlands", "season": null, "topic": "see"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 1647914e17ba28e6 | Amsterdam | see | summer | yes | yes | 1 | 1 |
| 35b6eff8c2c4fcbf | Amsterdam | see | None | yes | yes | 3 | 3 |

Cause guess: No observed difference for the labeled relevant chunks.

## walking tours in Athens

Extracted filters: {"city": "Athens", "country": "Greece", "season": null, "topic": "do"}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 87487288845bb046 | Athens | see | summer | yes | no | 1 | absent |
| ed0703e1cb235ca3 | Athens | do | None | yes | yes | 2 | 1 |

Cause guess: Query expansion/fusion or the 30-candidate cutoff likely displaced relevant candidates.

## train station tips in Milan

Extracted filters: {"city": "Milan", "country": "Italy", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 3a7cf6a63c488592 | Milan | get in | None | yes | yes | 1 | 1 |
| a393b6ef278a6f13 | Milan | drink | None | yes | yes | 10 | 17 |

Cause guess: Candidate composition or ordering changed; compare expansion/fusion and reranking.

## best local wine in Seville

Extracted filters: {"city": "Seville", "country": "Spain", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 59599b3079d35576 | Seville | do | summer | yes | yes | 2 | 2 |
| 89f1ed41ff188278 | Seville | do | None | yes | yes | 1 | 1 |

Cause guess: No observed difference for the labeled relevant chunks.

## outdoor activities in Lyon

Extracted filters: {"city": "Lyon", "country": "France", "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| da282ccafde86c1e | Lyon | drink | None | yes | yes | 4 | 4 |

Cause guess: No observed difference for the labeled relevant chunks.

## historic sites in France

Extracted filters: {"city": null, "country": null, "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 31f059781d899a5e | Florence | understand | None | yes | yes | 28 | 28 |
| 3f7f37bf202c4f8d | Lyon | see | None | yes | yes | 12 | 12 |
| df6d6db27347bf6e | Paris | see | None | yes | yes | 2 | 2 |

Cause guess: No observed difference for the labeled relevant chunks.

## quiet cafés in Italy

Extracted filters: {"city": null, "country": null, "season": null, "topic": null}

| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 0440211f65e3d66d | Valencia | see | None | yes | yes | 20 | 20 |
| 79598fa843004ce8 | Milan | eat | None | yes | yes | 1 | 1 |
| 73a2425b86cb8033 | Milan | drink | None | yes | yes | 4 | 4 |

Cause guess: No observed difference for the labeled relevant chunks.
