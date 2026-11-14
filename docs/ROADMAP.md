# Stato e sviluppo

## v0.1 — base operativa

- Package e CLI con core senza dipendenze ML, runtime pesanti isolati.
- Tre skill installabili e workflow quality/fast.
- Inbox stabile, deduplicazione, checkpoint, retry, lock e servizio macOS.
- Parakeet/Qwen, Whisper selettivo, Nemotron/Community, rapporto e Markdown.
- Glossari per progetto/lingua con hotword Qwen e alias segnalati.
- Enrollment vocale da audio reale, embedding versionati, suggerimenti/unknown e politica di accettazione esplicita.
- Revisione di nomi e testo; correzioni riallineate quando l'allineatore è configurato.
- GitHub Actions sui test del core; audio e inference esclusi dalla CI.

## Prossimo incremento — qualità misurata

1. Etichettare un piccolo insieme italiano/inglese con passaggi segnalati e campioni non segnalati. Separare taratura e verifica.
2. Confermare nomi e campioni puliti di interlocutori abituali, da più riunioni. Includere sconosciuti e condizioni acustiche diverse nella verifica.
3. Misurare errori di testo, omissioni, falsi nomi, errori lasciati passare e tempo umano. I punteggi decoder non bastano.
4. Accorpare avvisi vicini e migliorare il filtro: il primo insieme di soglie è conservativo e può produrre molti avvisi.
5. Allineare entrambe le letture per localizzare i disaccordi a livello di parola; introdurre sostituzioni automatiche soltanto su classi validate.
6. Aggiungere confronto/riconciliazione dei cluster speaker e revisione delle frontiere, oltre al conteggio e alla conferma dei nomi.

## Integrazioni successive

- Verificare l'export realmente disponibile da Comu Starter sul Mac; aggiungere un adattatore sorgente quando il trasferimento è riproducibile.
- Integrare un VAD indipendente per controllare omissioni e silenzi.
- UI locale interattiva per correggere senza comandi e notificare solo quando serve.
- Esportazione Obsidian con destinazione per progetto, riassunti separati dalla trascrizione e collegamenti alle note esistenti.
- Pacchetto unico del runtime Mac e verifica di installazione pulita; gestione degli aggiornamenti dei modelli con benchmark di regressione.

Il servizio automatico può essere attivo prima di questi incrementi: produrrà bozze e richieste di revisione. Il riconoscimento dei nomi ad alta affidabilità dipende dalla banca vocale e da una valutazione reale, non dalla sola installazione del software.
