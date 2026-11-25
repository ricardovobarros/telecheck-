$signature = @'
using System;
using System.Runtime.InteropServices;
public static class TelecheckConsole {
    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll")]
    public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();
}
'@
Add-Type -TypeDefinition $signature

$hwnd = [TelecheckConsole]::GetConsoleWindow()
if ($hwnd -eq [IntPtr]::Zero) { exit 0 }

$GWL_EXSTYLE = -20
$WS_EX_TOOLWINDOW = 0x00000080
$WS_EX_APPWINDOW = 0x00040000
$style = [TelecheckConsole]::GetWindowLong($hwnd, $GWL_EXSTYLE)
$style = ($style -bor $WS_EX_TOOLWINDOW) -band (-bnot $WS_EX_APPWINDOW)
[void][TelecheckConsole]::SetWindowLong($hwnd, $GWL_EXSTYLE, $style)
# SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
[void][TelecheckConsole]::SetWindowPos($hwnd, [IntPtr]::Zero, 0, 0, 0, 0, 0x0037)
[void][TelecheckConsole]::ShowWindow($hwnd, 0)
[void][TelecheckConsole]::ShowWindow($hwnd, 8)
