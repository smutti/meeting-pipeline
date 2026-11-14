# Prima versione e pipeline locale: osservazioni del 14 novembre 2026

**Esito:** è stato superato il limite architetturale di quattro speaker ed è operativo un workflow locale con più letture e audit. Non è ancora misurato un miglioramento di WER, DER o tempo umano di revisione. Il testo selezionato dal workflow coincide ancora con Parakeet; nessuna correzione è stata approvata automaticamente.

Qui **V1** indica il precedente workflow basato su Vibe/Whisper e Sortformer a quattro canali; **V2** indica il motore locale di questo repository. Non sono due tag Git: il repository nasce con V2. Il vecchio adattatore controllava una matrice con quattro colonne e iterava su quattro canali. I nomi nelle note archiviate erano stati assegnati manualmente e potevano superare il numero di canali del modello.

## Corpus e configurazione

Due registrazioni private: IT-A, italiano, 1.419,987 s (~23:40), sette partecipanti che avrebbero parlato secondo l'utente; EN-B, inglese prevalente, 3.411,828 s (~56:52), quattro interlocutori dichiarati, stanza grande e audio riverberante. Il conteggio dell'utente non sostituisce l'annotazione dei turni. Le note archiviate conservano alcune modifiche umane; non sono ground truth. Nel file inglese terminano a 3.407,05 s, prima della fine del WAV.

Tutti i nuovi motori ricevono lo stesso WAV mono 16 kHz PCM16, senza denoise o correzione del volume. Il decoder ha segnalato pacchetti MP3 non validi sul file inglese, con durata decodificata inferiore di ~0,32 s al contenitore. Gli originali restano invariati. Tre campioni di 90 s per audio sono stati scelti per posizione temporale prima di vedere le risposte: 9 minuti totali, senza riferimento umano completato.

Hardware: Apple M5 Pro, 24 GB. MLX 0.32.4, mlx-audio 0.6.5, mlx-whisper 0.4.3. Revisioni:

| Componente | Revisione |
|---|---|
| Whisper large-v3 MLX | `49e6aa286ad60c14352c404340ded53710378a11` |
| Qwen3-ASR 1.7B BF16 MLX | `e1f6c266914abc5a46e8756e02580f834a6cf8a7` |
| Parakeet Ultra Core ML | `95eaa59a39d4394f047a4dc5cce480388a60d1b6` |
| FluidAudio | `16780f04d2ece24f67d0fc00efccd0296491c1a8` |
| Nemotron-3 Diarization | `52a432672732425e4c19765b9fec9b5810e6f4ba` |
| NeMo-Speech.cpp | binario 0.3.0, converter `e790e463b2913cff9f989a3df224c587f14b4c5c` |
| Community-1 Core ML | `7eab74f3463c736418d0eb10296261ae581146c9` |

Parakeet usa encoder INT8 per canale; Whisper FP16, Qwen BF16; Nemotron GGUF contiene 358 tensori F32 e una convoluzione F16. Queste sono implementazioni e precisioni specifiche, non un confronto delle sole architetture teoriche. Qwen usa chunk da 90 s, temperatura 0; Whisper usa il normale fallback di decodifica. Una prova preliminare greedy è conservata separatamente e non entra nella tabella principale.

## Inferenza ASR sul file intero

| Motore | IT-A, secondi | EN-B, secondi |
|---|---:|---:|
| Whisper large-v3 / MLX | 104,49 | 306,35 |
| Qwen3-ASR 1.7B / MLX | 73,94 | 121,27 |
| Parakeet Ultra / Core ML | 8,29 | 18,70 |

Una esecuzione per configurazione, modelli già scaricati. Il caricamento iniziale MLX è escluso; l'avvio del comando Core ML è incluso. Sono misure indicative, non medie ripetute né confronto dei tempi della vecchia app Vibe. I tempi non dicono quale testo sia più fedele.

Nel file inglese Whisper ripete una stessa breve frase 18 volte nell'intervallo circa 38:30–38:54; gli altri due output hanno testo diverso. È un'anomalia osservata negli output, da verificare sull'audio. Non viene conteggiata come errore certificato in assenza del riferimento umano.

## Diarizzazione

| Configurazione | IT-A | EN-B | Interpretazione |
|---|---:|---:|---|
| V1 Sortformer 4 canali | capacità massima 4 | capacità massima 4 | Limite dell'adattatore precedente, non misura su questi file |
| Nemotron-3 automatico | 7 | 4 | Conteggio rilevato |
| Community-1 Core ML automatico | 6 | 3 | Conteggio rilevato |
| Community-1 Core ML con numero fornito | 7 | 4 | Conteggio imposto come vincolo |

Nemotron supporta al massimo [otto speaker](https://huggingface.co/nvidia/Nemotron-3-Diarization). Il workflow sceglie Community-1 se l'utente dichiara più di otto voci. Non è una promessa di diarizzazione illimitata o corretta.

Il settimo cluster italiano di Nemotron contiene solo 3,868 s; il più breve inglese solo 1,696 s. Il conteggio corrisponde alle attese, ma potrebbe includere frammentazione della stessa voce. Senza turni annotati e mappatura delle etichette non possiamo calcolare DER. Community-1 con numero noto non è una conferma indipendente del numero reale.

## Workflow completo V2

Le seguenti prove usano la ricetta `quality` del codice a commit `cd1ded5`, con il runtime operativo fuori dalle cartelle protette di macOS. Il benchmark ASR sopra è separato. La versione del package è 0.1.0; il commit viene annotato qui perché il manifest iniziale registrava soltanto la versione del package.

| Misura | IT-A | EN-B |
|---|---:|---:|
| Tempo end-to-end osservato | 138,97 s | 179,70 s |
| Segnalazioni aperte | 67 | 151 |
| Letture Whisper mirate | 6 | 2 |
| Audio coperto dall'unione degli intervalli segnalati | 97,2% | 97,3% |
| Sostituzioni del testo approvate | 0 | 0 |
| Stato finale | `needs_review` | `needs_review` |

Il tempo end-to-end è la differenza tra creazione e ultimo aggiornamento del job, senza revisione umana. I controlli includono bassi punteggi del decoder, allineamento degli speaker, disaccordi, speaker molto brevi e identità sconosciute. Le finestre di controllo sono larghe: la copertura del 97% **non equivale al 97% di parole sbagliate**, né al tempo effettivo richiesto a una persona. Mostra però che non è ancora dimostrata una riduzione sostanziale dell'ascolto manuale.

Il testo selezionato è identico, confrontando le parole separate da spazi, al Parakeet del benchmark su entrambi i file. Qwen e Whisper aggiungono alternative e segnalazioni; questa versione non sceglie automaticamente il testo migliore. I profili vocali non sono ancora iscritti; il glossario contiene soltanto un nome di progetto per registrazione. Non è stato misurato un vantaggio né del riconoscimento dei nomi né del glossario.

Una prova precedente sul file italiano aveva 46 segnalazioni: mancava il successivo controllo dell'allineamento degli speaker. È conservata nel confronto locale, ma non viene usata per stimare un miglioramento o una regressione rispetto alle 67 segnalazioni attuali.

I [dati aggregati](benchmark-2026-11-14.json) sono pubblici; registrazioni, testi, nomi, percorsi e profili restano privati. I risultati del corpus privato sono osservazioni riportate dall'autore, non verificabili indipendentemente senza gli audio. Il [protocollo](EVALUATION.md) e il codice consentono di ripetere il metodo su un corpus proprio. Per dimostrare il “prima/dopo” di accuratezza servono ora riferimenti umani sugli stessi intervalli, turni speaker annotati e misure del lavoro di revisione.
