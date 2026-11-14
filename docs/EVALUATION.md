# Confrontare le trascrizioni

Il confronto ha tre livelli separati:

1. **Output:** archivio della prima versione, ASR indipendenti, testo selezionato dal workflow e revisioni umane. Conservare per ogni variante sorgente, versione, parametri, tempi e interventi umani.
2. **Fedeltà:** WER su campioni con riferimento umano, errori su nomi/numeri/negazioni/termini, diarizzazione contro turni annotati e identità contro etichette confermate.
3. **Operatività:** tempo end-to-end, secondi di audio da rivedere, minuti di revisione effettivi, errori sfuggiti ai controlli. Il numero di segnalazioni da solo non misura né qualità né lavoro risparmiato.

Le note archiviate possono essere già corrette: non usarle come ground truth senza riascolto. La versione MLX di Whisper e la precedente inferenza whisper.cpp sono configurazioni differenti; il benchmark nuovo non ricostruisce automaticamente i tempi o gli errori della vecchia applicazione.

## Rapporto locale riproducibile

`scripts/compare_transcripts.py` usa solo la libreria standard e non esegue inferenza. Legge un manifest JSON privato, genera HTML offline, riepilogo Markdown e misure JSON. Conservare input e output fuori dal checkout, oppure sotto `evaluations/` ignorata da Git.

Schema minimo sintetico:

```json
{
  "recordings": [{
    "id": "IT-A", "label": "Registrazione di test", "duration": 90,
    "audio": "file:///percorso/audio.wav",
    "variants": [
      {"id": "archive", "label": "Archivio", "text": "Testo precedente",
       "notes": "Revisione manuale non verificata",
       "segments": [{"start": 0, "end": 10, "text": "Testo precedente"}]},
      {"id": "candidate", "label": "Candidato", "text": "Testo nuovo",
       "segments": [{"start": 0, "end": 10, "text": "Testo nuovo"}]}
    ]
  }],
  "clips": [{
    "id": "IT-A-1", "recording": "IT-A", "start": 0, "duration": 90,
    "audio": "file:///percorso/campione.wav",
    "candidates": [{"variant": "candidate", "scope": "exact_clip", "text": "Testo nuovo"}]
  }]
}
```

La prima variante è il riferimento **testuale di archivio**, non il riferimento di correttezza. Il rapporto mostra `1 − SequenceMatcher.ratio` su parole normalizzate, disattivando `autojunk`: è una distanza descrittiva dal testo archiviato, non WER. Un valore maggiore può significare sia correzioni sia nuovi errori. Segmenti grossolani vengono mostrati interi se intersecano l'intervallo scelto; la vista temporale non inventa allineamenti.

```sh
python scripts/compare_transcripts.py /percorso/manifest.json --output /percorso/confronto
# Aprire comparison.html, ascoltare e scaricare references.json.
python scripts/compare_transcripts.py /percorso/manifest.json \
  --output /percorso/confronto --references /percorso/references.json
```

Riferimenti:

```json
[{"clip_id":"IT-A-1","text":"Testo verificato ascoltando","human_reviewed":true}]
```

L'HTML mantiene le proposte chiuse inizialmente; salvare il riferimento prima di guardarle riduce il condizionamento, senza eliminarlo. È possibile ricaricare il JSON per proseguire. Il testo non è salvato automaticamente quando si chiude la pagina. Il rapporto contiene materiale privato e non va pubblicato.

## Cosa calcola lo script

WER = distanza di Levenshtein tra parole / numero di parole del riferimento. Normalizzazione: Unicode NFKC, minuscole, apostrofi uniformati, punteggiatura rimossa. Accenti, negazioni e numeri restano distinti; non si espandono cifre in parole. Riportare queste scelte perché influenzano i punteggi. Gli aggregati sommano edit e parole, non fanno la media delle percentuali. WER può superare 1 in presenza di molte inserzioni.

Sono ammessi solo riferimenti dichiarati `human_reviewed: true` e candidati `scope: exact_clip`. La dichiarazione è responsabilità del revisore: il software non può verificarne l'ascolto. Estratti da segmenti larghi sono `approximate`, esclusi dalla misura. Per confrontare un workflow completo contro i campioni, preparare ipotesi sugli stessi esatti confini, verificando le parole ai bordi; non etichettare automaticamente una selezione per timestamp come `exact_clip`.

Gli estratti decodificati separatamente misurano quel modo di inferenza: non dimostrano la WER dello stesso modello sul file intero. Includere almeno un insieme rappresentativo scelto prima di leggere le risposte e un insieme difficile separato. Su pochi campioni riportare valori e copertura, senza generalizzare ad altre riunioni. La prima raccolta contiene sei campioni di 90 s: 9 minuti complessivi.

## Misure ancora da raccogliere

- **Diarizzazione:** annotare chi parla e quando, incluse sovrapposizioni. Calcolare DER con mappatura delle etichette, dichiarando collar e trattamento degli overlap. Il report attuale non implementa DER.
- **Identità:** separare riunioni di iscrizione, calibrazione e test; includere voci sconosciute e misurare false attribuzioni e astensioni. Il numero di speaker non valuta il riconoscimento dei nomi.
- **Glossario:** confrontare stesso audio, stesso modello e parametri, con e senza termini; contare termini corretti e sostituzioni spurie. Non confrontare una versione già corretta da una persona con un output grezzo come prova dell'effetto del glossario.
- **Tempo:** ripetere le prove, separare cold/warm start, caricamento, normalizzazione, inferenza, revisione e durata complessiva. Il benchmark iniziale contiene una sola esecuzione per configurazione.
- **Revisione:** cronometrare il lavoro umano e ascoltare anche passaggi non segnalati. Abbassare le soglie senza questo controllo potrebbe nascondere errori invece di ridurre il lavoro.
