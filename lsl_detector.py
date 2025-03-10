from pylsl import resolve_streams

def detectar_senales_lsl():
    print("🔍 Buscando señales LSL en la red...")
    streams = resolve_streams()  # Eliminado el argumento timeout

    if not streams:
        print("❌ No se encontraron streams LSL en la red.")
        return

    print(f"✅ Se encontraron {len(streams)} stream(s):\n")
    
    for i, stream in enumerate(streams):
        print(f"🔹 Stream {i+1}:")
        print(f"   ▶ Nombre: {stream.name()}")
        print(f"   ▶ Tipo: {stream.type()}")
        print(f"   ▶ ID Único: {stream.source_id()}")
        print(f"   ▶ Frecuencia de muestreo: {stream.nominal_srate()} Hz")
        print(f"   ▶ Número de canales: {stream.channel_count()}")
        print(f"   ▶ Formato de datos: {stream.channel_format()}")
        print(f"   ▶ Host: {stream.hostname()}\n")

if __name__ == "__main__":
    detectar_senales_lsl()
