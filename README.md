# HCC100 Local (ha-hcc100-ble)

Integrazione personalizzata per **Home Assistant** e client Bluetooth locale per
il controller **Resideo HCC100**. Questa repository contiene **solo il componente**:
codice dell'integrazione, client BLE, test e strumenti di collaudo.

> La ricerca, il reverse engineering del protocollo e il percorso completo di come
> è stata ottenuta la decodifica sono documentati in una repository separata e privata:
> [`mtshare/hcc100-local`](https://github.com/mtshare/hcc100-local).

**Collaudo reale riuscito:** il Bluetooth del Raspberry Pi 4 con HA OS ha
completato l'handshake autonomo e letto le quattro zone dell'HCC100, senza app
iPhone o chiavi catturate. L'integrazione è caricata nel Core reale: 17 entità su
quattro zone. Il funzionamento prolungato resta da misurare.

## Che cosa fa questa prima versione

- Esegue un handshake P-256 autonomo a ogni nuova connessione.
- Legge gli stati logici delle uscite aperte/chiuse, separati per zona.
- Espone stato delle uscite, numero di uscite aperte, temperatura e setpoint.
- Usa il Bluetooth gestito da Home Assistant, compreso quello integrato del
  Raspberry Pi 4. Non richiede un iPhone, Frida, cloud o chiavi catturate.
- Ricorda il certificato del controller scelto e rifiuta cambiamenti inattesi.
- Conserva una connessione e interroga il controller ogni 60 secondi; l'intervallo
  può essere regolato fra 15 e 300 secondi.

La prima versione è **di sola lettura**: non imposta temperature, non cambia
configurazioni, non forza valvole e non attiva test dell'impianto. Il controllo
climate verrà aggiunto soltanto dopo aver verificato i comandi di scrittura.

Lo stato logico di un'uscita non misura la posizione meccanica dell'attuatore e
non viene presentato automaticamente come richiesta di calore della stanza.

## Hardware

Il Bluetooth integrato del **Raspberry Pi 4B è supportato da Home Assistant**.
Partire da quello: una chiavetta USB o un proxy possono essere valutati se il
collaudo evidenzia problemi di portata. Non è richiesta una radio RAMSES/evofw3.

Il controller può richiedere una breve pressione del tasto per rendere disponibile
il collegamento BLE. Durante l'uso del client, l'app tecnica deve lasciare libera
la connessione al controller.

Fonti: [Bluetooth in Home Assistant](https://www.home-assistant.io/integrations/bluetooth/),
[API per le integrazioni BLE](https://contributors.home-assistant.io/core/integrations/bluetooth/).

## Installazione in Home Assistant OS

Target iniziale: **Home Assistant 2026.11.0**, Raspberry Pi 4, 64 bit.

Seguire [l'installazione su HA OS](docs/INSTALLAZIONE_HA_OS.md). La cartella da
installare è `custom_components/hcc100_local`; le dipendenze Bluetooth e
crittografiche vengono fornite dal Core e dall'integrazione Bluetooth di HA.
Non installare pacchetti di sistema sul Raspberry per questo componente.

`hacs.json` prepara la struttura per HACS, ma per questa repository privata il
percorso documentato e verificabile è l'installazione manuale del pacchetto.

## Client da terminale

Con Python 3.13 o successivo:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/hcc100-ble scan
.venv/bin/hcc100-ble info --address AA:BB:CC:DD:EE:FF
.venv/bin/hcc100-ble state --address AA:BB:CC:DD:EE:FF
```

`info` restituisce anche l'impronta del certificato. Nelle prove successive si può
passarla con `--pin IMPRONTA_SHA256`. L'integrazione HA la salva automaticamente
nel config entry. Su macOS l'indirizzo è un UUID CoreBluetooth; quello dell'iPhone
non è trasferibile al Raspberry: usare la scansione dell'adattatore interessato.

`state --watch 60` conserva la sessione e aggiorna le letture. La libreria del
protocollo è la stessa impiegata dall'integrazione HA, senza copie divergenti.

## Verifica senza installare nulla nel Core

È disponibile una prova temporanea per un HA OS già raggiungibile via SSH:

```sh
.venv/bin/python tools/pi_probe.py smoke --ssh hassio
.venv/bin/python tools/pi_probe.py scan --ssh hassio
.venv/bin/python tools/pi_probe.py state --ssh hassio --address AA:BB:CC:DD:EE:FF
```

Il programma trasferisce il sorgente in una directory temporanea nel contenitore
esistente, usa le librerie già presenti, poi elimina la directory. Non scrive in
`/config`, non installa pacchetti, non crea configurazioni HA e non riavvia servizi.

## Test e pacchetto

```sh
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python tools/build_bundle.py
```

Il file `dist/hcc100-local-0.1.0.zip` contiene soltanto il componente e le sue
traduzioni.

## Documentazione di ricerca

Protocollo, handshake, percorso delle chiavi, validazione e storia dell'indagine
sono mantenuti nella repository privata di ricerca
[`mtshare/hcc100-local`](https://github.com/mtshare/hcc100-local):

- Percorso completo, chiavi e archivio delle prove
- Protocollo e handshake osservati
- Risultati dei collaudi e limiti
- Storia dell'indagine e correzioni

I campioni di test qui presenti sono sintetici. La repository non contiene app iOS,
firmware proprietario, catture personali, chiavi di sessione o credenziali Home Assistant.
