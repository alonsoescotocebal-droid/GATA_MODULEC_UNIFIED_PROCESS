function ConvertTo-NativeProcessArgument {
    [CmdletBinding()]
    param(
        [AllowNull()][string]$Value
    )

    if ($null -eq $Value -or $Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Format-NativeProcessCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    $parts = @($FilePath) + @($ArgumentList)
    return (($parts | ForEach-Object { ConvertTo-NativeProcessArgument $_ }) -join ' ')
}

function Invoke-NativeProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory=$true)][string]$WorkingDirectory,
        [Parameter(Mandatory=$true)][string]$StdoutPath,
        [Parameter(Mandatory=$true)][string]$StderrPath
    )

    foreach ($logPath in @($StdoutPath, $StderrPath)) {
        $parent = Split-Path -Parent $logPath
        if ($parent) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    }

    $launchFilePath = $FilePath
    $launchArguments = @($ArgumentList)
    $extension = [IO.Path]::GetExtension($FilePath).ToLowerInvariant()
    $commandLine = $null
    if ($extension -in @('.bat', '.cmd')) {
        $bridgePath = Join-Path $PSScriptRoot 'native_process_bridge.py'
        if (-not (Test-Path -LiteralPath $bridgePath)) { throw "NATIVE_PROCESS_BRIDGE_MISSING: $bridgePath" }
        $bridgePython = (Get-Command python.exe -ErrorAction Stop).Source
        $encodedArguments = [Convert]::ToBase64String(
            [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -Compress @($ArgumentList)))
        )
        $launchFilePath = $bridgePython
        $launchArguments = @(
            $bridgePath,
            '--file-path', $FilePath,
            '--working-directory', $WorkingDirectory,
            '--args-json-b64', $encodedArguments
        )
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $launchFilePath
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    if ($null -ne $commandLine) {
        $startInfo.Arguments = '/d /s /c "' + $commandLine + '"'
    }
    else {
        $startInfo.Arguments = (($launchArguments | ForEach-Object { ConvertTo-NativeProcessArgument $_ }) -join ' ')
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw "NATIVE_PROCESS_START_FAILED: $FilePath" }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    [IO.File]::WriteAllText($StdoutPath, $stdout, (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($StderrPath, $stderr, (New-Object System.Text.UTF8Encoding($false)))
    return [int]$process.ExitCode
}
