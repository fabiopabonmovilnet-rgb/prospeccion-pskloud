using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

class PSKloudLauncher
{
    [DllImport("kernel32.dll")]
    static extern IntPtr GetConsoleWindow();

    [DllImport("user32.dll")]
    static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    static void Main()
    {
        Console.Title = "PSKloud Prospector v2.0";
        ShowWindow(GetConsoleWindow(), 3); // SW_MAXIMIZE

        string projectDir = @"C:\Users\fabio\prospeccion-pskloud";
        Environment.CurrentDirectory = projectDir;

        Console.WriteLine(@"============================================");
        Console.WriteLine(@"  PSKloud Prospector v2.0");
        Console.WriteLine(@"  Sistema REAL de Prospeccion B2B");
        Console.WriteLine(@"============================================");
        Console.WriteLine();
        Console.WriteLine(@"  Iniciando servidor Streamlit...");
        Console.WriteLine(@"  Abrira en: http://localhost:8501");
        Console.WriteLine();
        Console.WriteLine(@"  IMPORTANTE: Manten esta ventana ABIERTA");
        Console.WriteLine(@"  mientras usas la aplicacion.");
        Console.WriteLine();
        Console.WriteLine(@"  Para cerrar: cierra esta ventana");
        Console.WriteLine(@"  o presiona Ctrl+C");
        Console.WriteLine();

        if (!File.Exists(Path.Combine(projectDir, "app.py")))
        {
            Console.WriteLine(@"  ERROR: No se encuentra app.py");
            Console.WriteLine(@"  Ruta esperada: " + projectDir);
            Pause();
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo("http://localhost:8501")
            {
                UseShellExecute = true
            });
        }
        catch { }

        var psi = new ProcessStartInfo("streamlit", "run app.py")
        {
            WorkingDirectory = projectDir,
            UseShellExecute = true
        };

        try
        {
            using (var proc = Process.Start(psi))
            {
                proc.WaitForExit();
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine(@"  ERROR al iniciar Streamlit:");
            Console.WriteLine(@"  " + ex.Message);
            Console.WriteLine();
            Console.WriteLine(@"  Asegurate de tener instalado:");
            Console.WriteLine(@"  pip install streamlit pandas openpyxl requests");
            Pause();
        }
    }

    static void Pause()
    {
        Console.WriteLine();
        Console.Write(@"  Presiona ENTER para salir...");
        Console.ReadLine();
    }
}
