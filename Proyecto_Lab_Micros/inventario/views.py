from django.shortcuts import render, redirect
from django.core.paginator import Paginator

# Cumple Req. 2.4 (Escalabilidad >= 30 artículos individuales) y Req. 2.1 (ID único por pieza)
INVENTARIO_ITEMS = [
    # Microcontroladores y Tarjetas de Desarrollo
    {'id': 1, 'id_unico': 'MIC-ESP32-001', 'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'SoC Xtensa Dual-Core 32-bit LX6, Wi-Fi/BLE, 38 pines GPIO, incluye cable Micro-USB.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 2, 'id_unico': 'MIC-ESP32-002', 'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'SoC Xtensa Dual-Core 32-bit LX6, Wi-Fi/BLE, 38 pines GPIO, incluye cable Micro-USB.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 3, 'id_unico': 'MIC-ESP32-003', 'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 1', 'estatus': 'PRESTADO', 'especificaciones': 'SoC Xtensa Dual-Core 32-bit LX6, Wi-Fi/BLE, 38 pines GPIO, incluye cable Micro-USB.', 'observaciones': 'En préstamo activo', 'motivo_baja': ''},
    {'id': 4, 'id_unico': 'MIC-PIC16-001', 'nombre': 'Kit Microcontrolador PIC16F887 + Grabador PICkit 3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 8 bits DIP-40, 20 MHz, incluye programador/depurador ICSP USB y base ZIF.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 5, 'id_unico': 'MIC-PIC16-002', 'nombre': 'Kit Microcontrolador PIC16F887 + Grabador PICkit 3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 8 bits DIP-40, 20 MHz, incluye programador/depurador ICSP USB y base ZIF.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 6, 'id_unico': 'MIC-PIC16-003', 'nombre': 'Kit Microcontrolador PIC16F887 + Grabador PICkit 3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 2', 'estatus': 'MANTENIMIENTO', 'especificaciones': 'MCU 8 bits DIP-40, 20 MHz, incluye programador/depurador ICSP USB y base ZIF.', 'observaciones': 'Revisión de zócalo ZIF con falso contacto.', 'motivo_baja': ''},
    {'id': 7, 'id_unico': 'MIC-MEGA-001', 'nombre': 'Arduino Mega 2560 Rev3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'ATmega2560 16MHz, 54 pines digitales I/O, 16 entradas analógicas, 4 UARTs.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 8, 'id_unico': 'MIC-MEGA-002', 'nombre': 'Arduino Mega 2560 Rev3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'ATmega2560 16MHz, 54 pines digitales I/O, 16 entradas analógicas, 4 UARTs.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 9, 'id_unico': 'MIC-STM32-001', 'nombre': 'Tarjeta ARM Cortex-M4 STM32F401RE Nucleo-64', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 32-bit 84 MHz, 512 KB Flash, depurador ST-LINK/V2-1 integrado.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 10, 'id_unico': 'MIC-STM32-002', 'nombre': 'Tarjeta ARM Cortex-M4 STM32F401RE Nucleo-64', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 32-bit 84 MHz, 512 KB Flash, depurador ST-LINK/V2-1 integrado.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 11, 'id_unico': 'MIC-8086-001', 'nombre': 'Entrenador de Microprocesador Intel 8086 / 8088', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Tablero didáctico con teclado hexadecimal, display 7 segmentos y puertos PPI 8255.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 12, 'id_unico': 'MIC-8086-002', 'nombre': 'Entrenador de Microprocesador Intel 8086 / 8088', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Tablero didáctico con teclado hexadecimal, display 7 segmentos y puertos PPI 8255.', 'observaciones': '', 'motivo_baja': ''},

    # Instrumentos de Medición y Fuentes de Poder
    {'id': 13, 'id_unico': 'INS-OSC-001', 'nombre': 'Osciloscopio Digital Tektronix TBS1102B 100MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales analógicos, muestreo 2 GS/s, pantalla LCD 7 pulgadas, análisis FFT.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 14, 'id_unico': 'INS-OSC-002', 'nombre': 'Osciloscopio Digital Tektronix TBS1102B 100MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 1', 'estatus': 'MANTENIMIENTO', 'especificaciones': '2 canales analógicos, muestreo 2 GS/s, pantalla LCD 7 pulgadas, análisis FFT.', 'observaciones': 'Calibración de canal CH2 pendiente.', 'motivo_baja': ''},
    {'id': 15, 'id_unico': 'INS-OSC-003', 'nombre': 'Osciloscopio Digital Tektronix TBS1102B 100MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales analógicos, muestreo 2 GS/s, pantalla LCD 7 pulgadas, análisis FFT.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 16, 'id_unico': 'INS-FUE-001', 'nombre': 'Fuente de Alimentación DC Regulada Triple Salida (0-30V / 5A)', 'categoria': 'Fuentes de Poder', 'estante': 'Estante B', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': '2 salidas variables 0-30V 5A + 1 salida fija 5V 3A para lógica TTL/CMOS, protección contra cortocircuito.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 17, 'id_unico': 'INS-FUE-002', 'nombre': 'Fuente de Alimentación DC Regulada Triple Salida (0-30V / 5A)', 'categoria': 'Fuentes de Poder', 'estante': 'Estante B', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': '2 salidas variables 0-30V 5A + 1 salida fija 5V 3A para lógica TTL/CMOS, protección contra cortocircuito.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 18, 'id_unico': 'INS-FUE-003', 'nombre': 'Fuente de Alimentación DC Regulada Triple Salida (0-30V / 5A)', 'categoria': 'Fuentes de Poder', 'estante': 'Estante B', 'cajon': 'Cajón 2', 'estatus': 'PRESTADO', 'especificaciones': '2 salidas variables 0-30V 5A + 1 salida fija 5V 3A para lógica TTL/CMOS, protección contra cortocircuito.', 'observaciones': 'Prestado en mesa 4', 'motivo_baja': ''},
    {'id': 19, 'id_unico': 'INS-GEN-001', 'nombre': 'Generador de Funciones Arbitrarias Rigol DG1022Z 25MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales de salida, señales senoidal, cuadrada (reloj), rampa, pulso y ruido.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 20, 'id_unico': 'INS-GEN-002', 'nombre': 'Generador de Funciones Arbitrarias Rigol DG1022Z 25MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales de salida, señales senoidal, cuadrada (reloj), rampa, pulso y ruido.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 21, 'id_unico': 'INS-MUL-001', 'nombre': 'Multímetro Digital True-RMS Fluke 115', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Medición de voltaje AC/DC 600V, corriente 10A, continuidad audible, frecuencia y capacitancia.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 22, 'id_unico': 'INS-MUL-002', 'nombre': 'Multímetro Digital True-RMS Fluke 115', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Medición de voltaje AC/DC 600V, corriente 10A, continuidad audible, frecuencia y capacitancia.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 23, 'id_unico': 'INS-MUL-003', 'nombre': 'Multímetro Digital True-RMS Fluke 115', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 4', 'estatus': 'DANADO', 'especificaciones': 'Medición de voltaje AC/DC 600V, corriente 10A, continuidad audible, frecuencia y capacitancia.', 'observaciones': 'Fusible interno de 10A quemado en práctica.', 'motivo_baja': ''},
    {'id': 24, 'id_unico': 'INS-ANA-001', 'nombre': 'Analizador Lógico USB de 8 Canales 24MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Decodificación de protocolos I2C, SPI, UART, 1-Wire y CAN para depuración de microprocesadores.', 'observaciones': '', 'motivo_baja': ''},

    # Cables, Puntas de Prueba y Accesorios
    {'id': 25, 'id_unico': 'CAB-OSC-001', 'nombre': 'Punta de Prueba Atenuada para Osciloscopio BNC (1x/10x)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'Ancho de banda 100MHz, conector BNC macho con gancho retráctil y caimán de tierra.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 26, 'id_unico': 'CAB-OSC-002', 'nombre': 'Punta de Prueba Atenuada para Osciloscopio BNC (1x/10x)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'Ancho de banda 100MHz, conector BNC macho con gancho retráctil y caimán de tierra.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 27, 'id_unico': 'CAB-OSC-003', 'nombre': 'Punta de Prueba Atenuada para Osciloscopio BNC (1x/10x)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'Ancho de banda 100MHz, conector BNC macho con gancho retráctil y caimán de tierra.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 28, 'id_unico': 'CAB-BNC-001', 'nombre': 'Cable Coaxial BNC a Caimán-Caimán (Generador / Osciloscopio)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'Impedancia 50 Ohms, 1 metro de longitud, terminales caimán rojo (señal) y negro (GND).', 'observaciones': '', 'motivo_baja': ''},
    {'id': 29, 'id_unico': 'CAB-BNC-002', 'nombre': 'Cable Coaxial BNC a Caimán-Caimán (Generador / Osciloscopio)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'Impedancia 50 Ohms, 1 metro de longitud, terminales caimán rojo (señal) y negro (GND).', 'observaciones': '', 'motivo_baja': ''},
    {'id': 30, 'id_unico': 'CAB-CAI-001', 'nombre': 'Juego de 10 Cables Caimán-Caimán Multicolor (50 cm)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'Pinzas caimán aisladas de 35mm para interconexión rápida de circuitos y alimentación.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 31, 'id_unico': 'CAB-CAI-002', 'nombre': 'Juego de 10 Cables Caimán-Caimán Multicolor (50 cm)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'Pinzas caimán aisladas de 35mm para interconexión rápida de circuitos y alimentación.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 32, 'id_unico': 'CAB-BAN-001', 'nombre': 'Par de Cables Banana a Caimán para Fuente de Alimentación', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Calibre 18 AWG siliconado, soporta hasta 10A para alimentar protoboards desde fuente DC.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 33, 'id_unico': 'CAB-BAN-002', 'nombre': 'Par de Cables Banana a Caimán para Fuente de Alimentación', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Calibre 18 AWG siliconado, soporta hasta 10A para alimentar protoboards desde fuente DC.', 'observaciones': '', 'motivo_baja': ''},

    # Unidades adicionales para completar cinco piezas de cada modelo
    {'id': 34, 'id_unico': 'MIC-ESP32-004', 'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'SoC Xtensa Dual-Core 32-bit LX6, Wi-Fi/BLE, 38 pines GPIO, incluye cable Micro-USB.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 35, 'id_unico': 'MIC-ESP32-005', 'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'SoC Xtensa Dual-Core 32-bit LX6, Wi-Fi/BLE, 38 pines GPIO, incluye cable Micro-USB.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 36, 'id_unico': 'MIC-PIC16-004', 'nombre': 'Kit Microcontrolador PIC16F887 + Grabador PICkit 3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 8 bits DIP-40, 20 MHz, incluye programador/depurador ICSP USB y base ZIF.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 37, 'id_unico': 'MIC-PIC16-005', 'nombre': 'Kit Microcontrolador PIC16F887 + Grabador PICkit 3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 8 bits DIP-40, 20 MHz, incluye programador/depurador ICSP USB y base ZIF.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 38, 'id_unico': 'MIC-MEGA-003', 'nombre': 'Arduino Mega 2560 Rev3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'ATmega2560 16MHz, 54 pines digitales I/O, 16 entradas analógicas, 4 UARTs.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 39, 'id_unico': 'MIC-MEGA-004', 'nombre': 'Arduino Mega 2560 Rev3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'ATmega2560 16MHz, 54 pines digitales I/O, 16 entradas analógicas, 4 UARTs.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 40, 'id_unico': 'MIC-MEGA-005', 'nombre': 'Arduino Mega 2560 Rev3', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'ATmega2560 16MHz, 54 pines digitales I/O, 16 entradas analógicas, 4 UARTs.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 41, 'id_unico': 'MIC-STM32-003', 'nombre': 'Tarjeta ARM Cortex-M4 STM32F401RE Nucleo-64', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 32-bit 84 MHz, 512 KB Flash, depurador ST-LINK/V2-1 integrado.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 42, 'id_unico': 'MIC-STM32-004', 'nombre': 'Tarjeta ARM Cortex-M4 STM32F401RE Nucleo-64', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 32-bit 84 MHz, 512 KB Flash, depurador ST-LINK/V2-1 integrado.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 43, 'id_unico': 'MIC-STM32-005', 'nombre': 'Tarjeta ARM Cortex-M4 STM32F401RE Nucleo-64', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'MCU 32-bit 84 MHz, 512 KB Flash, depurador ST-LINK/V2-1 integrado.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 44, 'id_unico': 'MIC-8086-003', 'nombre': 'Entrenador de Microprocesador Intel 8086 / 8088', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Tablero didáctico con teclado hexadecimal, display 7 segmentos y puertos PPI 8255.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 45, 'id_unico': 'MIC-8086-004', 'nombre': 'Entrenador de Microprocesador Intel 8086 / 8088', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Tablero didáctico con teclado hexadecimal, display 7 segmentos y puertos PPI 8255.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 46, 'id_unico': 'MIC-8086-005', 'nombre': 'Entrenador de Microprocesador Intel 8086 / 8088', 'categoria': 'Microcontroladores', 'estante': 'Estante A', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Tablero didáctico con teclado hexadecimal, display 7 segmentos y puertos PPI 8255.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 47, 'id_unico': 'INS-OSC-004', 'nombre': 'Osciloscopio Digital Tektronix TBS1102B 100MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales analógicos, muestreo 2 GS/s, pantalla LCD 7 pulgadas, análisis FFT.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 48, 'id_unico': 'INS-OSC-005', 'nombre': 'Osciloscopio Digital Tektronix TBS1102B 100MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales analógicos, muestreo 2 GS/s, pantalla LCD 7 pulgadas, análisis FFT.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 49, 'id_unico': 'INS-FUE-004', 'nombre': 'Fuente de Alimentación DC Regulada Triple Salida (0-30V / 5A)', 'categoria': 'Fuentes de Poder', 'estante': 'Estante B', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': '2 salidas variables 0-30V 5A + 1 salida fija 5V 3A para lógica TTL/CMOS, protección contra cortocircuito.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 50, 'id_unico': 'INS-FUE-005', 'nombre': 'Fuente de Alimentación DC Regulada Triple Salida (0-30V / 5A)', 'categoria': 'Fuentes de Poder', 'estante': 'Estante B', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': '2 salidas variables 0-30V 5A + 1 salida fija 5V 3A para lógica TTL/CMOS, protección contra cortocircuito.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 51, 'id_unico': 'INS-GEN-003', 'nombre': 'Generador de Funciones Arbitrarias Rigol DG1022Z 25MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales de salida, señales senoidal, cuadrada (reloj), rampa, pulso y ruido.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 52, 'id_unico': 'INS-GEN-004', 'nombre': 'Generador de Funciones Arbitrarias Rigol DG1022Z 25MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales de salida, señales senoidal, cuadrada (reloj), rampa, pulso y ruido.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 53, 'id_unico': 'INS-GEN-005', 'nombre': 'Generador de Funciones Arbitrarias Rigol DG1022Z 25MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': '2 canales de salida, señales senoidal, cuadrada (reloj), rampa, pulso y ruido.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 54, 'id_unico': 'INS-MUL-004', 'nombre': 'Multímetro Digital True-RMS Fluke 115', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Medición de voltaje AC/DC 600V, corriente 10A, continuidad audible, frecuencia y capacitancia.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 55, 'id_unico': 'INS-MUL-005', 'nombre': 'Multímetro Digital True-RMS Fluke 115', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Medición de voltaje AC/DC 600V, corriente 10A, continuidad audible, frecuencia y capacitancia.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 56, 'id_unico': 'INS-ANA-002', 'nombre': 'Analizador Lógico USB de 8 Canales 24MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Decodificación de protocolos I2C, SPI, UART, 1-Wire y CAN para depuración de microprocesadores.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 57, 'id_unico': 'INS-ANA-003', 'nombre': 'Analizador Lógico USB de 8 Canales 24MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Decodificación de protocolos I2C, SPI, UART, 1-Wire y CAN para depuración de microprocesadores.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 58, 'id_unico': 'INS-ANA-004', 'nombre': 'Analizador Lógico USB de 8 Canales 24MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Decodificación de protocolos I2C, SPI, UART, 1-Wire y CAN para depuración de microprocesadores.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 59, 'id_unico': 'INS-ANA-005', 'nombre': 'Analizador Lógico USB de 8 Canales 24MHz', 'categoria': 'Instrumentos de Medición', 'estante': 'Estante B', 'cajon': 'Cajón 5', 'estatus': 'DISPONIBLE', 'especificaciones': 'Decodificación de protocolos I2C, SPI, UART, 1-Wire y CAN para depuración de microprocesadores.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 60, 'id_unico': 'CAB-OSC-004', 'nombre': 'Punta de Prueba Atenuada para Osciloscopio BNC (1x/10x)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'Ancho de banda 100MHz, conector BNC macho con gancho retráctil y caimán de tierra.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 61, 'id_unico': 'CAB-OSC-005', 'nombre': 'Punta de Prueba Atenuada para Osciloscopio BNC (1x/10x)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 1', 'estatus': 'DISPONIBLE', 'especificaciones': 'Ancho de banda 100MHz, conector BNC macho con gancho retráctil y caimán de tierra.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 62, 'id_unico': 'CAB-BNC-003', 'nombre': 'Cable Coaxial BNC a Caimán-Caimán (Generador / Osciloscopio)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'Impedancia 50 Ohms, 1 metro de longitud, terminales caimán rojo (señal) y negro (GND).', 'observaciones': '', 'motivo_baja': ''},
    {'id': 63, 'id_unico': 'CAB-BNC-004', 'nombre': 'Cable Coaxial BNC a Caimán-Caimán (Generador / Osciloscopio)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'Impedancia 50 Ohms, 1 metro de longitud, terminales caimán rojo (señal) y negro (GND).', 'observaciones': '', 'motivo_baja': ''},
    {'id': 64, 'id_unico': 'CAB-BNC-005', 'nombre': 'Cable Coaxial BNC a Caimán-Caimán (Generador / Osciloscopio)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 2', 'estatus': 'DISPONIBLE', 'especificaciones': 'Impedancia 50 Ohms, 1 metro de longitud, terminales caimán rojo (señal) y negro (GND).', 'observaciones': '', 'motivo_baja': ''},
    {'id': 65, 'id_unico': 'CAB-CAI-003', 'nombre': 'Juego de 10 Cables Caimán-Caimán Multicolor (50 cm)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'Pinzas caimán aisladas de 35mm para interconexión rápida de circuitos y alimentación.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 66, 'id_unico': 'CAB-CAI-004', 'nombre': 'Juego de 10 Cables Caimán-Caimán Multicolor (50 cm)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'Pinzas caimán aisladas de 35mm para interconexión rápida de circuitos y alimentación.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 67, 'id_unico': 'CAB-CAI-005', 'nombre': 'Juego de 10 Cables Caimán-Caimán Multicolor (50 cm)', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 3', 'estatus': 'DISPONIBLE', 'especificaciones': 'Pinzas caimán aisladas de 35mm para interconexión rápida de circuitos y alimentación.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 68, 'id_unico': 'CAB-BAN-003', 'nombre': 'Par de Cables Banana a Caimán para Fuente de Alimentación', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Calibre 18 AWG siliconado, soporta hasta 10A para alimentar protoboards desde fuente DC.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 69, 'id_unico': 'CAB-BAN-004', 'nombre': 'Par de Cables Banana a Caimán para Fuente de Alimentación', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Calibre 18 AWG siliconado, soporta hasta 10A para alimentar protoboards desde fuente DC.', 'observaciones': '', 'motivo_baja': ''},
    {'id': 70, 'id_unico': 'CAB-BAN-005', 'nombre': 'Par de Cables Banana a Caimán para Fuente de Alimentación', 'categoria': 'Cables y Puntas de Prueba', 'estante': 'Estante C', 'cajon': 'Cajón 4', 'estatus': 'DISPONIBLE', 'especificaciones': 'Calibre 18 AWG siliconado, soporta hasta 10A para alimentar protoboards desde fuente DC.', 'observaciones': '', 'motivo_baja': ''},
]

CATEGORIAS_SISTEMA = [
    'Microcontroladores',
    'Instrumentos de Medición',
    'Fuentes de Poder',
    'Cables y Puntas de Prueba',
]

ETIQUETAS_ESTATUS = {
    'DISPONIBLE': 'Disponible',
    'PRESTADO': 'Prestado',
    'MANTENIMIENTO': 'En mantenimiento',
    'DANADO': 'Dañado',
    'BAJA_DEFINITIVA': 'Dado de baja',
}


def _preparar_item_vista(item):
    copia = dict(item)
    copia['estatus_display'] = ETIQUETAS_ESTATUS.get(item['estatus'], item['estatus'])
    copia['dado_de_baja'] = item['estatus'] == 'BAJA_DEFINITIVA'
    return copia


# Pantalla 13: Tabla de Inventario General con ordenamiento, filtros y paginación (Req. 2.0, 2.3, 6.0.1)
def gestion_inventario(request):
    query = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '').strip()
    estatus = request.GET.get('estatus', '').strip()
    # Por defecto incluimos las bajas definitivas dentro del inventario para trazabilidad en Admin y Laboratorista
    incluir_bajas = request.GET.get('bajas', '1') != '0'

    materiales = [
        _preparar_item_vista(m)
        for m in INVENTARIO_ITEMS
        if incluir_bajas or m['estatus'] != 'BAJA_DEFINITIVA'
    ]

    if query:
        q_low = query.lower()
        materiales = [
            m for m in materiales
            if q_low in m['nombre'].lower()
            or q_low in m['id_unico'].lower()
            or q_low in m['estante'].lower()
            or q_low in m['cajon'].lower()
            or q_low in (m.get('motivo_baja') or '').lower()
        ]
    if categoria:
        materiales = [m for m in materiales if m['categoria'] == categoria]
    if estatus:
        materiales = [m for m in materiales if m['estatus'] == estatus]

    campos_orden = ('id_unico', 'nombre', 'categoria', 'ubicacion', 'estatus')
    orden = request.GET.get('orden', 'id_unico')
    if orden not in campos_orden:
        orden = 'id_unico'
    direccion = request.GET.get('direccion', 'asc')
    if direccion not in ('asc', 'desc'):
        direccion = 'asc'
    claves_orden = {
        'id_unico': lambda item: item['id_unico'].lower(),
        'nombre': lambda item: item['nombre'].lower(),
        'categoria': lambda item: item['categoria'].lower(),
        'ubicacion': lambda item: (item['estante'] + item['cajon']).lower(),
        'estatus': lambda item: item['estatus_display'].lower(),
    }
    materiales.sort(key=claves_orden[orden], reverse=direccion == 'desc')
    total_registros = len(materiales)
    page_obj = Paginator(materiales, 20).get_page(request.GET.get('page'))

    query_params = request.GET.copy()
    query_params.pop('page', None)
    enlaces_orden = {}
    for campo in campos_orden:
        parametros = request.GET.copy()
        parametros['orden'] = campo
        parametros['direccion'] = (
            'desc'
            if request.GET.get('orden') == campo
            and request.GET.get('direccion') == 'asc'
            else 'asc'
        )
        parametros.pop('page', None)
        enlaces_orden[campo] = parametros.urlencode()

    context = {
        'materiales': page_obj.object_list,
        'total_registros': total_registros,
        'query': query,
        'categoria_sel': categoria,
        'estatus_sel': estatus,
        'incluir_bajas': incluir_bajas,
        'categorias': CATEGORIAS_SISTEMA,
        'mensaje_exito': request.session.pop('mensaje_exito', None),
        'page_obj': page_obj,
        'query_params': query_params.urlencode(),
        'enlaces_orden': enlaces_orden,
    }
    return render(request, 'inventario/gestion_inventario.html', context)


# Pantalla 18 (Parte A): Formulario de Alta de Materiales con generación de IDs únicos y Códigos de Barras (Req. 2.1, 2.1.1)
def nuevo_material(request):
    ids_generados = []
    error_msg = None
    datos_previos = {}

    if request.method == 'POST':
        descripcion = request.POST.get('descripcion', '').strip()
        categoria = request.POST.get('categoria', 'Microcontroladores').strip()
        especificaciones = request.POST.get('especificaciones', '').strip()
        estante = request.POST.get('estante', 'Estante A').strip()
        cajon = request.POST.get('cajon', 'Cajón 1').strip()
        cantidad_str = request.POST.get('cantidad', '1').strip()

        datos_previos = {
            'descripcion': descripcion,
            'categoria': categoria,
            'especificaciones': especificaciones,
            'estante': estante,
            'cajon': cajon,
            'cantidad': cantidad_str,
        }

        if not descripcion or not cantidad_str.isdigit() or int(cantidad_str) < 1:
            error_msg = 'Por favor ingresa la descripción obligatoria del material y una cantidad válida (mínimo 1 unidad).'
        else:
            cantidad = int(cantidad_str)
            prefijos = {
                'Microcontroladores': 'MIC',
                'Instrumentos de Medición': 'INS',
                'Fuentes de Poder': 'FUE',
                'Cables y Puntas de Prueba': 'CAB',
            }
            pref = prefijos.get(categoria, 'MAT')
            sub = ''.join([c for c in descripcion.upper() if c.isalnum()])[:4] or 'EQP'

            for _ in range(cantidad):
                nuevo_id = len(INVENTARIO_ITEMS) + 1
                id_unico = f"{pref}-{sub}-{nuevo_id:03d}"
                nuevo_item = {
                    'id': nuevo_id,
                    'id_unico': id_unico,
                    'nombre': descripcion,
                    'categoria': categoria,
                    'estante': estante,
                    'cajon': cajon,
                    'estatus': 'DISPONIBLE',
                    'especificaciones': especificaciones or 'Equipo estándar del Laboratorio de Microprocesadores.',
                    'observaciones': 'Alta de lote nuevo.',
                    'motivo_baja': '',
                }
                INVENTARIO_ITEMS.append(nuevo_item)
                ids_generados.append(_preparar_item_vista(nuevo_item))

    return render(request, 'inventario/formulario_material.html', {
        'categorias': CATEGORIAS_SISTEMA,
        'ids_generados': ids_generados,
        'error_msg': error_msg,
        'datos': datos_previos,
    })


# Pantalla 18 (Parte B): Edición de Ubicación, Cambio de Mantenimiento a Disponible y Baja Definitiva (Req. 2.2, 5.2, 5.2.1, 4.1.1)
def editar_material(request, item_id):
    material = next((m for m in INVENTARIO_ITEMS if m['id'] == item_id), None)
    if not material:
        return redirect('inventario:gestion')

    error_msg = None
    if request.method == 'POST':
        accion = request.POST.get('tipo_accion', 'ubicacion')

        # 1) Modificar ubicación física (Estante y Cajón - Req. 2.2)
        if accion == 'ubicacion':
            estante = request.POST.get('estante', '').strip()
            cajon = request.POST.get('cajon', '').strip()
            if estante and cajon:
                material['estante'] = estante
                material['cajon'] = cajon
                request.session['mensaje_exito'] = f"Ubicación de {material['id_unico']} actualizada a {estante}, {cajon}."
                return redirect('inventario:gestion')
            else:
                error_msg = "Debes especificar tanto el número de estante como el número de cajón."

        # 2) Cambiar de En Mantenimiento / Dañado a Disponible o viceversa (Req. 5.2.1)
        elif accion == 'estatus':
            nuevo_estatus = request.POST.get('nuevo_estatus', '').strip()
            observacion = request.POST.get('observaciones', '').strip()
            if not observacion:
                error_msg = "Es obligatorio registrar una observación técnica al cambiar el estatus del equipo."
            else:
                material['estatus'] = nuevo_estatus
                material['observaciones'] = observacion
                request.session['mensaje_exito'] = f"Estatus del equipo {material['id_unico']} actualizado correctamente."
                return redirect('inventario:gestion')

        # 3) Dar de Baja Definitiva con motivo obligatorio (Req. 5.2 y 5.2.1)
        elif accion == 'baja':
            motivo = request.POST.get('motivo_baja', '').strip()
            if not motivo:
                error_msg = "Debes seleccionar obligatoriamente un motivo de baja del menú desplegable."
            else:
                material['estatus'] = 'BAJA_DEFINITIVA'
                material['motivo_baja'] = motivo
                request.session['mensaje_exito'] = f"El equipo {material['id_unico']} fue dado de Baja Definitiva ({motivo}). Se conserva en el inventario para auditoría."
                return redirect('inventario:gestion')

    return render(request, 'inventario/editar_material.html', {
        'material': _preparar_item_vista(material),
        'error_msg': error_msg,
    })

