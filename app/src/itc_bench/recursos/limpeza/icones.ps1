# Organizar ícones da Área de Trabalho (ADR-083), vem depois de inicializacao/comum.ps1.
# ITC_SIDS: SIDs separados por vírgula, escolhidos na tela. Liga "Organizar ícones
# automaticamente" (0x1) e "Alinhar ícones à grade" (0x4) em FFlags da Área de Trabalho, como o
# botão direito > Exibir. Conta sem sessão: hive carregado e descarregado (comum.ps1).
# Saída: OK|<sid> ou ERRO|<sid>|<codigo>; nunca caminho.
$BAGS = 'Software\Microsoft\Windows\Shell\Bags\1\Desktop'
$PADRAO = 0x40200225  # o que o Windows grava com as duas opções ligadas
$contas = @{}
foreach ($c in Contas) { $contas[$c.Sid] = $c }

try {
    foreach ($sid in (([string]$env:ITC_SIDS) -split ',')) {
        if ($sid -notmatch '^S-1-5-21-[0-9-]+$') { continue }
        if (-not $contas.ContainsKey($sid)) { Write-Output "ERRO|$sid|sem_conta"; continue }
        try {
            $h = Hive-Usuario $contas[$sid]
            if (-not $h) { Write-Output "ERRO|$sid|conta_em_uso"; continue }
            $k = $HKU.CreateSubKey("$h\$BAGS")
            [void]$script:abertas.Add($k)
            $atual = $k.GetValue('FFlags')
            $novo = if ($atual -is [int]) { $atual -bor 0x5 } else { $PADRAO }
            $k.SetValue('FFlags', [int]$novo, [Microsoft.Win32.RegistryValueKind]::DWord)
            Write-Output "OK|$sid"
        } catch { Write-Output "ERRO|$sid|falhou" }
    }
} finally {
    Fechar-Hives
}
