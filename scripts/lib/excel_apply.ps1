param(
  [Parameter(Mandatory = $true)][string]$Src,
  [Parameter(Mandatory = $true)][string]$Dst,
  [string]$Edits = ""
)
# Opens $Src in a private Excel instance, applies JSON edits (optional),
# runs a full recalculation and saves to $Dst. All non-ASCII text (sheet
# names, formulas, comments) comes from the UTF-8 JSON file, never from here.
$ErrorActionPreference = "Stop"
$sw = [System.Diagnostics.Stopwatch]::StartNew()

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class XlWin {
  [DllImport("user32.dll")]
  public static extern int GetWindowThreadProcessId(IntPtr hWnd, out int processId);
}
"@

function To-XlValue($x) {
  # ConvertFrom-Json (PS 5.1) yields Decimal/Int32/Int64; Excel COM wants Double.
  if ($x -is [decimal] -or $x -is [int] -or $x -is [long] -or $x -is [single]) { return [double]$x }
  return $x
}

function Set-ComProp($obj, [string]$name, $value) {
  # PS 5.1 caches a COM property's argument type on first assignment (a double
  # written to Value2 makes later strings/arrays fail with InvalidCastException).
  # InvokeMember goes straight through IDispatch and bypasses that cache.
  if ($value -is [System.Management.Automation.PSObject]) { $value = $value.psobject.BaseObject }
  $argv = New-Object object[] 1
  $argv[0] = $value
  [void][System.__ComObject].InvokeMember($name, [System.Reflection.BindingFlags]::SetProperty, $null, $obj, $argv)
}

$xl = New-Object -ComObject Excel.Application
$xlPid = 0
[XlWin]::GetWindowThreadProcessId([IntPtr]$xl.Hwnd, [ref]$xlPid) | Out-Null
$xl.Visible = $false
$xl.DisplayAlerts = $false
$xl.AskToUpdateLinks = $false
$xl.ScreenUpdating = $false
$xl.EnableEvents = $false
$counts = @{}
try {
  $wb = $xl.Workbooks.Open($Src, 0, $false)
  $xl.Calculation = -4135
  if ($Edits -ne "") {
    $ops = Get-Content -Path $Edits -Raw -Encoding UTF8 | ConvertFrom-Json
    $n = 0
    foreach ($op in $ops) {
      $n++
      try {
        switch ($op.op) {
          "formula" {
            Set-ComProp ($wb.Worksheets.Item($op.sheet).Range($op.cell)) "Formula" ([string]$op.value)
          }
          "value" {
            Set-ComProp ($wb.Worksheets.Item($op.sheet).Range($op.cell)) "Value2" (To-XlValue $op.value)
          }
          "clear" {
            $wb.Worksheets.Item($op.sheet).Range($op.range).ClearContents() | Out-Null
          }
          "comment" {
            $r = $wb.Worksheets.Item($op.sheet).Range($op.cell)
            $old = ""
            if ($r.Comment -ne $null) { $old = $r.Comment.Text() + "`n"; $r.Comment.Delete() }
            $c = $r.AddComment($old + [string]$op.text)
            $c.Shape.Width = 260
            $c.Shape.Height = 90
          }
          "addsheet" {
            $last = $wb.Worksheets.Item($wb.Worksheets.Count)
            $new = $wb.Worksheets.Add([System.Reflection.Missing]::Value, $last)
            $new.Name = [string]$op.name
          }
          "breaklinks" {
            # Drop the workbook's links to other workbooks (xlExcelLinks = 1). Any formula still
            # referencing one is turned into its last value by Excel, so callers replace such
            # formulas first and use this only to remove the dangling link definitions.
            $links = $wb.LinkSources(1)
            if ($links -ne $null) { foreach ($l in @($links)) { $wb.BreakLink([string]$l, 1); "broke link: $l" } }
          }
          "table" {
            $ws = $wb.Worksheets.Item($op.sheet)
            $rows = @($op.rows)
            $nr = $rows.Count
            $nc = 0
            foreach ($row in $rows) { if (@($row).Count -gt $nc) { $nc = @($row).Count } }
            $arr = New-Object 'object[,]' $nr, $nc
            for ($i = 0; $i -lt $nr; $i++) {
              $cells = @($rows[$i])
              for ($j = 0; $j -lt $cells.Count; $j++) {
                # Inline casts store raw .NET values; PSObject wrappers inside object[,]
                # are not unwrapped by the COM marshaller ("Specified cast is not valid").
                $v = $cells[$j]
                if ($null -eq $v) { continue }
                if ($v -is [System.Management.Automation.PSObject]) { $v = $v.psobject.BaseObject }
                if ($v -is [decimal] -or $v -is [int] -or $v -is [long] -or $v -is [single] -or $v -is [double]) { $arr[$i, $j] = [double]$v }
                else { $arr[$i, $j] = [string]$v }
              }
            }
            $target = $ws.Range($op.cell).Resize($nr, $nc)
            Set-ComProp $target "Value2" $arr
            if ($op.header) {
              $ws.Range($op.cell).Resize(1, $nc).Font.Bold = $true
              $target.Columns.AutoFit() | Out-Null
              foreach ($col in $target.Columns) { if ($col.ColumnWidth -gt 60) { $col.ColumnWidth = 60 } }
            }
          }
          "style" {
            $rg = $wb.Worksheets.Item($op.sheet).Range($op.range)
            if ($op.numfmt) { Set-ComProp $rg "NumberFormat" ([string]$op.numfmt) }
            if ($op.bold -ne $null) { Set-ComProp $rg.Font "Bold" ([bool]$op.bold) }
            if ($op.italic -ne $null) { Set-ComProp $rg.Font "Italic" ([bool]$op.italic) }
            if ($op.size -ne $null) { Set-ComProp $rg.Font "Size" ([double]$op.size) }
            if ($op.color -ne $null) { Set-ComProp $rg.Font "Color" ([double]$op.color) }
            if ($op.fill -ne $null) { Set-ComProp $rg.Interior "Color" ([double]$op.fill) }
            if ($op.wrap -ne $null) { Set-ComProp $rg "WrapText" ([bool]$op.wrap) }
            if ($op.width -ne $null) { Set-ComProp $rg.EntireColumn "ColumnWidth" ([double]$op.width) }
          }
          default { throw "unknown op" }
        }
      }
      catch {
        throw ("op #{0} ({1} {2}!{3}{4}): {5}" -f $n, $op.op, $op.sheet, $op.cell, $op.range, $_.Exception.Message)
      }
      if ($counts.ContainsKey($op.op)) { $counts[$op.op]++ } else { $counts[$op.op] = 1 }
    }
  }
  $xl.Calculation = -4105
  $xl.CalculateFull()
  $wb.SaveAs($Dst, 51)
  $wb.Close($false)
  $summary = ($counts.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join " "
  "OK ops: $summary ; seconds=" + [int]$sw.Elapsed.TotalSeconds
}
finally {
  $xl.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
  Start-Sleep -Seconds 2
  $p = Get-Process -Id $xlPid -ErrorAction SilentlyContinue
  if ($p -ne $null) { Stop-Process -Id $xlPid -Force; "stopped private Excel pid $xlPid" }
}
