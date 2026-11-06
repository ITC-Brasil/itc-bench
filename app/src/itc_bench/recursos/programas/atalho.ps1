# Atalhos dos Web Apps no Desktop Público (ADR-020). Dados só por ITC_*; nada interpolado em comando.
# ITC_ACAO: listar | criar | apagar. ITC_PASTA: Desktop Público.
$sh = New-Object -ComObject WScript.Shell
switch ($env:ITC_ACAO) {
    'listar' {
        $itens = @(Get-ChildItem -LiteralPath $env:ITC_PASTA -Filter '*.lnk' -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                $l = $sh.CreateShortcut($_.FullName)
                [pscustomobject]@{ nome = $_.Name; descricao = $l.Description; argumentos = $l.Arguments }
            })
        ConvertTo-Json -InputObject $itens -Compress
    }
    'criar' {
        $destino = Join-Path $env:ITC_PASTA $env:ITC_NOME
        $l = $sh.CreateShortcut($destino)
        $l.TargetPath = $env:ITC_ALVO
        $l.Arguments = $env:ITC_ARGUMENTOS
        $l.WorkingDirectory = Split-Path -Parent $env:ITC_ALVO
        $l.Description = 'ITC Bench'
        if ($env:ITC_ICONE) { $l.IconLocation = $env:ITC_ICONE + ',0' }
        $l.Save()
        'OK'
    }
    'apagar' {
        $destino = Join-Path $env:ITC_PASTA $env:ITC_NOME
        $l = $sh.CreateShortcut($destino)
        if ((Test-Path -LiteralPath $destino -PathType Leaf) -and $l.Description -eq 'ITC Bench') {
            Remove-Item -LiteralPath $destino -Force
            'OK'
        } else { 'RECUSADO' }
    }
    default { throw 'acao invalida' }
}
