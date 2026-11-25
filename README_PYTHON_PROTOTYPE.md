# OSSC Python Prototype

This is a temporary Python implementation of an OSSC server and agent.
It lets multiple clients register to a central server, pull scheduled
observation jobs, send heartbeat packets, execute server-issued commands,
and upload results.

## Start Server

```powershell
python ossc_server.py --host 0.0.0.0 --port 8080 --db ossc.sqlite3
```

Open `http://SERVER_IP:8080/` for the built-in user panel.

## Start Client Agent

Run this on every observed/observer machine:

```powershell
python ossc_client.py --server http://SERVER_IP:8080 --id client-a --name "Client A"
```

The agent polls the server, executes jobs assigned to its client id, and
posts the output back.

## Heartbeat

The agent registers once, then sends `POST /api/clients/heartbeat` every
poll loop. The server marks a client online when `now - last_seen <= 45s`
by default.

```powershell
Invoke-RestMethod http://localhost:8080/api/clients?heartbeat_timeout=120
```

## Manage Clients

The built-in panel has a Client Management form. You can:

```text
create a client manually
auto-discover clients from agent registration or heartbeat
edit name, probe address, and metadata
delete stale clients
```

`host` is the address reported by the agent heartbeat and may be a NAT
address. Do not use it as the probe destination. Configure `address`
manually in the panel; `target_client_ids` resolves to this configured
IP/domain when building command tasks.

Client management APIs:

```text
GET    /api/clients
PUT    /api/clients/{client_id}
DELETE /api/clients/{client_id}
POST   /api/clients/register
POST   /api/clients/heartbeat
```

## Create a Ping Task

```powershell
$body = @{
  name = "ping-from-a-to-b"
  type = "command"
  observer_ids = @("client-a")
  target_hosts = @("192.168.1.20")
  interval_seconds = 60
  params = @{
    mode = "foreground"
    command = @("ping", "-n", "4", "{target}")
    timeout = 20
  }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/tasks -Body $body -ContentType "application/json"
```

## Create an iperf3 Command Combo

The combo task sends three commands: start a background server command on
the target client, run a foreground client command on the observer, then
stop the target-side background process.

```powershell
$body = @{
  name = "iperf3-combo-a-to-b"
  type = "command_combo"
  observer_ids = @("client-a")
  target_client_ids = @("client-b")
  interval_seconds = 300
  params = @{
    steps = @(
      @{
        role = "target"
        delay_seconds = 0
        mode = "background"
        process_key = "iperf3-{target_client_id}-5201"
        command = @("iperf3", "-s", "-p", "5201")
      },
      @{
        role = "observer"
        delay_seconds = 2
        mode = "foreground"
        command = @("iperf3", "-c", "{target}", "-p", "5201", "-t", "10", "-J")
        timeout = 25
      },
      @{
        role = "target"
        delay_seconds = 14
        mode = "stop"
        process_key = "iperf3-{target_client_id}-5201"
      }
    )
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/tasks -Body $body -ContentType "application/json"
```

You can also pass explicit target hosts:

```powershell
$body = @{
  name = "iperf3-combo-a-to-b"
  type = "command_combo"
  observer_ids = @("client-a")
  target_clients = @(@{ id = "client-b"; host = "192.168.1.20" })
  interval_seconds = 300
  params = @{
    steps = @(
      @{
        role = "observer"
        delay_seconds = 0
        mode = "foreground"
        command = @("iperf3", "-c", "{target}", "-p", "5201", "-t", "10", "-J")
        timeout = 25
      }
    )
  }
} | ConvertTo-Json -Depth 6
```

For explicit targets, `address` and `host` are both accepted:

```powershell
target_clients = @(@{ id = "client-b"; address = "node-b.example.com" })
```

The agent has no built-in knowledge of `ping` or `iperf3`; they are just
commands sent by the server.

## Manage systemd Services

The built-in panel has a Service Management form for creating `systemctl`
command tasks. It supports:

```text
status, is-active, start, stop, restart, reload
```

Each selected client receives its own local command task, for example:

```text
systemctl status nginx.service --no-pager
```

The agent still treats this as a normal command. It does not have
systemd-specific logic, so Linux permissions apply as usual. Run the agent
with enough privileges or configure sudo/systemd policy separately when you
need to start, stop, or restart services.

## Inspect State

```powershell
Invoke-RestMethod http://localhost:8080/api/clients
Invoke-RestMethod http://localhost:8080/api/tasks
Invoke-RestMethod http://localhost:8080/api/results
```

## API Summary

- `POST /api/clients/register`
- `POST /api/clients/heartbeat`
- `GET /api/clients`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/agents/{client_id}/tasks`
- `POST /api/agents/{client_id}/results`
- `GET /api/results`
