# Installazione su Home Assistant OS

## Prima della copia

1. Verificare che HA mostri un adattatore funzionante nell'integrazione Bluetooth.
   Il Bluetooth integrato del Raspberry Pi 4 è sufficiente per iniziare.
2. Disconnettere Resideo Technician dal controller durante il collaudo.
3. Se necessario, usare una breve pressione del tasto Bluetooth del controller.
   Questa procedura non richiede reset, firmware o test delle uscite.
4. Usare una versione del componente verificata con la versione HA in uso.
   Il target iniziale è 2026.11.0.

## Copia del componente

Il pacchetto contiene:

```text
custom_components/
  hcc100_local/
    manifest.json
    ...
```

Con Terminal & SSH o Studio Code Server copiare la sola cartella `hcc100_local`
in `/config/custom_components/`. Non sostituire l'intera cartella
`custom_components`, `configuration.yaml`, `.storage` o le automazioni.

Se esiste già una versione di questo componente, conservarne una copia prima
dell'aggiornamento. La prima installazione di un custom component richiede un
riavvio del **Core di Home Assistant** per il riconoscimento. Pianificarlo in
un momento adatto alle automazioni dell'abitazione; non serve riavviare HA OS,
il Raspberry o il controller di riscaldamento.

Per evitare un'installazione prima del collaudo è disponibile `tools/pi_probe.py`:
usa un processo temporaneo nel Core esistente, senza scrivere nella configurazione
o riavviare il Core.

## Aggiunta nell'interfaccia

1. Impostazioni → Dispositivi e servizi → Aggiungi integrazione → **HCC100 Local**.
2. Se il dispositivo viene scoperto, l'indirizzo è proposto automaticamente.
   Altrimenti usare il MAC della scansione del Raspberry, non l'UUID dell'iPhone.
3. Lasciare libera la connessione dell'app tecnica e confermare.
4. Viene verificata una risposta cifrata del controller e salvata la sua impronta.

Usare una sola procedura di configurazione alla volta. Non avviare in parallelo
la sonda da terminale e l'aggiunta in HA: contenderebbero la stessa connessione.
Se il dispositivo è già stato aggiunto ma è in attesa di connessione, riaprire
la finestra BLE con il tasto fisico e ricaricare la sola integrazione esistente,
senza crearne una seconda e senza riavviare il Core.

L'aggiornamento iniziale crea un dispositivo controller e i dispositivi delle zone
configurate. I sensori mostrano temperatura, setpoint e numero delle uscite aperte;
un sensore binario indica se la zona ha almeno un'uscita logicamente aperta.

## Funzionamento e disponibilità

- L'intervallo predefinito è 60 secondi, regolabile nelle opzioni.
- Durante una sessione attiva il client conserva la connessione.
- Se il collegamento cade, gli stati diventano non disponibili. Un nuovo
  tentativo esegue un handshake nuovo, senza riusare chiavi vecchie.
- Il controller potrebbe richiedere nuovamente la pressione del tasto per
  riaprire la finestra BLE: questo vincolo deve essere misurato sul proprio impianto.
- La portata e la convivenza con altri dispositivi BLE vanno verificate prima
  di valutare un dongle o un proxy alternativo.

## Rimozione

Rimuovere il config entry di HCC100 Local dall'interfaccia; la connessione viene
chiusa e il polling arrestato. Rimuovere poi solo
`/config/custom_components/hcc100_local` se non serve più e riavviare il Core
quando opportuno. Il componente non crea automazioni, non cambia i parametri
del riscaldamento e non aggiorna il firmware.
