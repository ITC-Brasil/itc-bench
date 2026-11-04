# Coletor de rede (ADR-015): só coleta; APIPA, semIP e resumo ficam em Python.
$avisos = New-Object System.Collections.ArrayList
$r = [ordered]@{ adaptadores = @(); testes = @(); portas = @() }
try {
    $configs = @{}
    foreach ($c in @(Get-NetIPConfiguration -Detailed -ErrorAction SilentlyContinue)) { $configs[[string]$c.InterfaceIndex] = $c }
    $r.adaptadores = @(Get-NetAdapter | Sort-Object Status, Name | ForEach-Object {
        $cfg = $configs[[string]$_.ifIndex]
        $ipv4 = @(); $gw = $null; $dns = @(); $dhcp = $null
        if ($cfg) {
            $ipv4 = @($cfg.IPv4Address | ForEach-Object { $_.IPAddress })
            $gw = ($cfg.IPv4DefaultGateway | Select-Object -First 1).NextHop
            $dns = @($cfg.DNSServer | Where-Object { $_.AddressFamily -eq 2 } | ForEach-Object { $_.ServerAddresses })
            if ($cfg.NetIPv4Interface) { $dhcp = [string]$cfg.NetIPv4Interface.Dhcp }
        }
        [ordered]@{
            nome = $_.Name; descricao = $_.InterfaceDescription; status = [string]$_.Status
            tipoConexao = [string]$_.MediaType; macAddress = $_.MacAddress
            velocidadeMbps = $(if ($_.LinkSpeed) { [string]$_.LinkSpeed } else { $null })
            enderecosIPv4 = $ipv4; gateway = $gw; servidoresDNS = $dns; dhcp = $dhcp
        }
    })
} catch { [void]$avisos.Add('Falha ao listar adaptadores: ' + $_.Exception.Message) }
$testes = New-Object System.Collections.ArrayList
foreach ($alvo in @('8.8.8.8', '1.1.1.1')) {
    $t = [ordered]@{ tipo = 'ping'; alvo = $alvo; sucesso = $false; latenciaMs = $null; detalhe = $null }
    try {
        $p = Test-Connection -ComputerName $alvo -Count 2
        $t.sucesso = $true
        $t.latenciaMs = [math]::Round((($p | Measure-Object -Property ResponseTime -Average).Average), 0)
    } catch { $t.detalhe = $_.Exception.Message }
    [void]$testes.Add($t)
}
$t = [ordered]@{ tipo = 'resolucao-dns'; alvo = 'www.google.com'; sucesso = $false; latenciaMs = $null; detalhe = $null }
try {
    $d = Resolve-DnsName -Name 'www.google.com' -Type A | Where-Object { $_.IPAddress } | Select-Object -First 1
    $t.sucesso = $true; $t.detalhe = [string]$d.IPAddress
} catch { $t.detalhe = 'Falha na resolução: ' + $_.Exception.Message }
[void]$testes.Add($t)
$r.testes = @($testes)
try {
    $nomes = @{}
    foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) { $nomes[[string]$p.Id] = $p.ProcessName }
    $r.portas = @(Get-NetTCPConnection -State Listen | Sort-Object LocalPort -Unique | ForEach-Object {
        [ordered]@{ enderecoLocal = $_.LocalAddress; porta = $_.LocalPort; pid = $_.OwningProcess; processo = $nomes[[string]$_.OwningProcess] }
    })
} catch { [void]$avisos.Add('Falha ao listar portas em escuta: ' + $_.Exception.Message) }
$r.avisos = @($avisos)
$r | ConvertTo-Json -Depth 5 -Compress
