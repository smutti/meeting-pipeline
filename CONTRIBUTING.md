# Contribuire

Il progetto separa motore Python, adattatori locali, ricette e skill. Prima di aggiungere un backend leggere [ARCHITECTURE.md](docs/ARCHITECTURE.md); conservare output grezzi, provenienza e timestamp, e dichiarare i limiti del backend.

## Verifica locale

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src scripts
```

Questi controlli non richiedono modelli né registrazioni. L'inferenza attuale richiede un Mac Apple Silicon e il runtime separato documentato nel README.

Usare fixture sintetiche per i test. Non includere audio di riunioni, trascrizioni reali, credenziali, database, profili vocali o glossari personali. Un report HTML di confronto contiene testo e percorsi locali: è un dato privato, anche quando lo strumento che lo produce è pubblico.

Per modifiche alla qualità, descrivere corpus, versioni, parametri, normalizzazione, riferimento umano, hardware e modalità di misura. Valutare sullo stesso audio e riportare anche regressioni. Un numero corretto di speaker non basta a misurare la diarizzazione; il consenso tra ASR non è una verifica del testo.

Le pull request devono spiegare problema, comportamento risultante e verifiche. Il codice originale è MIT; dipendenze e modelli mantengono le rispettive licenze. Nuovi adattatori devono indicarne fonti e condizioni.
