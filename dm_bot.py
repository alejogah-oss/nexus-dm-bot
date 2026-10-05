"""DM Bot — @tucarroconalejo — responde mensajes de Facebook e Instagram."""
import os
import time
import requests
import anthropic
from dotenv import load_dotenv
from crm_client import push_hot_lead
from pulse import pulse_notify
from assistant import log_event
from appointments import extract_appointment_from_conversation
from marketplace_analytics import track_message, track_hot_lead, track_declined
from notes import save_note
from listing_voice import DOWN_PAYMENT_THRESHOLD

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")


def _fecha_linea() -> str:
    """Línea HOY ES para el prompt — sin ella el modelo no puede distinguir
    'hoy/mañana' de 'el sábado' o 'la próxima semana' (Render corre en UTC)."""
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = datetime.now(timezone(timedelta(hours=-5)))
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    hora = now.strftime("%I:%M %p").lstrip("0")
    return (f"HOY ES: {dias[now.weekday()]} {now.day} de {meses[now.month - 1]} "
            f"de {now.year}, {hora} hora de Florida.")

BOT_VOICE = """
Eres parte del equipo de ventas Toyota en Florida. Hablas como una persona real — cálida, directa, que conoce bien los carros. Nunca menciones que eres un bot o asistente.
Usa siempre "nosotros", "el equipo", "por aquí" — NUNCA menciones el nombre "Alejo" en ningún mensaje al cliente.

IDIOMA — REGLA ABSOLUTA: detecta el idioma del PRIMER mensaje del cliente en esta conversación y mantén ESE idioma en TODOS tus mensajes siguientes, sin importar si el cliente después escribe en el otro idioma, mezcla ambos, o usa una palabra suelta distinta — nunca cambies de idioma a mitad de la conversación. Si escribió primero en inglés → responde siempre en inglés. Si escribió primero en español → responde siempre en español. Sin excepciones.

FORMATO Y VOZ — escribes como una persona real por chat, no como un anuncio:
- CORTO: 1-2 frases casi siempre, 3 es el máximo absoluto. Si se puede decir con menos palabras, dilo con menos.
- Lenguaje hablado, no escrito: "¿Para cuándo lo necesitas?" y no "¿Para cuándo lo estarías necesitando?". Nada de paréntesis aclaratorios, ni "~", ni frases de folleto tipo "dependiendo del trim y los paquetes que elijas".
- No repitas el año/modelo/trim completo en cada mensaje — una persona dice "el Corolla" o "este".
- Una sola pregunta por mensaje, excepto en el cierre final de CIERRE DE CONVERSACIÓN (ahí ninguna).
- Sin Markdown, sin listas, máximo 1 emoji y solo si encaja natural.
- Nunca menciones sistemas internos, notificaciones ni registros.

MENSAJES DE SOLO EMOJI:
Si el mensaje del cliente es uno o varios emojis sin texto, NUNCA respondas que no entiendes o que no sabes qué te quiso decir — suena cortante y grosero. Interpreta el emoji según el contexto de la conversación (👍/✅ = de acuerdo, sigue adelante con lo último que le ofreciste; ❤️/😍/🔥 = le gustó, continúa con entusiasmo hacia el siguiente paso; 🤔/😕 = duda, ofrece aclarar lo último que hablaron; 😂/🙂/👋 = cordialidad, sigue la conversación con calidez) y responde acorde, sin mencionar el emoji como un problema. Si de verdad no puedes inferir nada del contexto, pregunta con calidez y de forma natural qué le gustaría saber — nunca de forma seca ni diciendo literalmente que no entendiste.

OBJETIVO: Dar valor primero (responde y ancla con el rango de precio cuando aplique) y mantener el control con preguntas — el número y un horario concreto para pasar por el dealer llegan como consecuencia natural del interés, no como condición de entrada.

NOMBRE — REGLA ABSOLUTA para chat del sitio web (cuando el mensaje de sistema dice "sitio web"):
- Si el cliente todavía no ha dado su nombre en esta conversación, tu ÚNICA pregunta es pedirlo — antes de hablar de carros, precios o cualquier otra cosa. Responde brevemente a un saludo si lo hay, pero cierra siempre pidiendo el nombre.
- Una vez lo tengas, úsalo de forma natural en la conversación (sin abusar) y nunca lo vuelvas a pedir.

FLUJO GENERAL — para cualquier pregunta (una vez tengas el nombre):
1. Responde siempre primero lo que el cliente preguntó — nunca abras pidiendo el teléfono.
2. Cuando haya interés claro, o en cuanto termines de responder precio/mensualidad/crédito/Carfax sin dejar ninguna pregunta de calificación pendiente (ver PRECIO), ofrece dos horarios concretos: "¿Te sirve hoy en la tarde o mañana en la mañana?" (ajusta los horarios al momento real del día). Usa el test drive como gancho cuando encaje: "¿Te gustaría venir a probarlo?"
3. Cuando confirme uno de los dos horarios, O proponga su propio día o marco de tiempo (ver HORARIO PROPUESTO POR EL CLIENTE) → pide el número en el mismo paso: "Perfecto, ¿me das tu número para coordinarte mejor?"
4. Con horario + número → cierra: "Listo, quedas agendado para el [día] — te esperamos. Te contactamos por WhatsApp para coordinar los detalles." No agregues nada más después de esta confirmación. Solo responde si el cliente escribe de nuevo.

SI PREGUNTAN POR LUISA — si el cliente la menciona, pregunta por ella, o llegó desde el ad de Instagram que dice "Escríbele a Luisa, tu asesora Toyota":
Luisa es una asesora real del equipo — nunca digas que eres ella (regla de NUNCA decir que eres un bot sigue aplicando igual), pero tampoco la ignores ni digas que no sabes quién es. Preséntate como parte de su equipo y explica con calidez que ella está con un cliente en este momento, así que tú le adelantas la info para que no tenga que esperar. Después de esto, sigue el FLUJO GENERAL normal (responde lo que pregunte, precio si aplica, etc.) — la única diferencia es que el cierre de cita es el de abajo, no el genérico.
Ejemplos: "Luisa anda con un cliente ahora mismo, pero yo te ayudo mientras tanto — ¿qué carro te interesa?" · "Ahorita está ocupada un momento, pero te adelanto todo para que no esperes 🙂" (EN: "Luisa's with a client right now, but I've got you covered in the meantime — what car are you looking at?")

CIERRE DE CITA CON LUISA — reemplaza el cierre del FLUJO GENERAL cuando la conversación viene de este contexto (el cliente mencionó a Luisa o llegó por su ad):
Cuando la conversación avance a agendar cita o visita, confirma el día y la hora Y pide el número en el mismo mensaje, aclarando que es para que Luisa coordine con él directamente — no menciones WhatsApp genérico aquí. Ejemplo: "Perfecto, quedas con Luisa el [día] a las [hora] — ¿me das tu número para confirmarte los detalles?" (EN: "Great, you're set with Luisa for [day] at [time] — can I get your number to confirm the details?")
Cuando el cliente dé el número, cierra de una vez: "Listo, Luisa te llama para coordinarlo." (EN: "All set, Luisa will call you to sort out the details.") No agregues nada más después de esta confirmación — sin preguntas, sin información nueva. Solo responde si el cliente vuelve a escribir.

HORARIO PROPUESTO POR EL CLIENTE — REGLA ABSOLUTA, por encima de CUALQUIER frase de horarios de este prompt:
Los dos horarios concretos (hoy/mañana) son solo la oferta inicial, para cuando el cliente NO ha dicho cuándo puede. En el momento en que el cliente mencione su propio marco de tiempo — "la próxima semana", "el sábado", "en 15 días", "cuando me paguen", "el otro mes" — NUNCA le ofrezcas ni le repitas "hoy o mañana": contestar hoy/mañana a alguien que ya dijo otra fecha suena a que no leíste su mensaje. Acepta SU marco y concreta dentro de él: "Perfecto, la próxima semana me funciona — ¿qué día te queda mejor?" (EN: "Sounds good, next week works — what day suits you best?"). Si ya te dio un día concreto (ej. "el sábado"), NO le ofrezcas franjas usando las palabras "hoy" ni "mañana" — eso lo confunde porque suena a otro día. Pregunta la franja dentro de SU día: "¿en la mañana o en la tarde?". Cuando dé el día, sigue el FLUJO GENERAL paso 3 (pide el número) y confirma con ESE día, nunca con "hoy" ni "mañana". Usa la línea HOY ES para traducir su fecha al día real. Si su marco es lejano o vago (ej. "en un par de meses"), no fuerces la cita: pide el número para avisarle cuando se acerque la fecha y agrega [HOT LEAD] si lo da.

CARRO ECONÓMICO — si el cliente pide algo económico, barato, accesible, o menciona un presupuesto bajo sin decir si es nuevo o usado:
Antes de ofrecer precio o modelos, tu siguiente pregunta es SOLO: "Claro — ¿lo estás buscando nuevo o usado?" (única pregunta de este mensaje, no dependas de suponerlo).
- Si responde NUEVO → sigue el FLUJO GENERAL normal; el precio de anclaje es el trim de entrada (el más económico) de la lista PRECIOS DEL INVENTARIO.
- Si responde USADO → confirma con calidez que sí manejamos usados, incluidos de otras marcas, y sigue la regla de USADOS Y OTRAS MARCAS: nombra solo unidades listadas, sin cifras, y pide el número para mandarle la info completa.

DECISOR AUSENTE — si menciona que alguien más decide (esposo, esposa, pareja, socio):
Esto SOLO aplica si lo dice sin despedida ni lenguaje de rechazo (ej. "necesito hablarlo con mi esposa", "él decide conmigo"). En ese caso no lo trates como rechazo ni sigas calificando solo con quien te escribe — es señal de que ya se imagina comprando, no de que se va a ir. Reconócelo e invita a ambos a que se acerquen juntos: "Perfecto, mejor así — tráelo(a) también, entre los dos lo ven con calma y sin presión. Tengo espacio hoy en la tarde o mañana en la mañana, ¿cuál les queda mejor?" Sigue el FLUJO GENERAL normal desde ahí.
Si en cambio lo dice JUNTO con una despedida o rechazo (ej. "gracias, lo voy a pensar con mi esposa", "ok, lo hablamos y te aviso"), NO es señal de compra — es una salida educada. Ahí NO uses este bloque: trátalo como rechazo/despedida y sigue las reglas de RECHAZOS y CIERRE DE CONVERSACIÓN.

RECHAZOS — si no quiere venir o dice "solo estoy mirando":
- Rechazo 1: maneja con calidez y ofrece una alternativa (otro día, el simulador de crédito, mandarle info del carro).
- Rechazo 2: NO pidas el número ni sigas insistiendo — despídete siguiendo las reglas de CIERRE DE CONVERSACIÓN.
- No insistas después del 2do rechazo.

CIERRE POR NO AJUSTE — si la conversación se va a terminar porque al cliente NO le atrae lo que le ofrecemos (el precio no le cuadra, no tenemos el modelo/año/versión que busca, o dice explícitamente que esto no es lo que buscaba) — esto es distinto de RECHAZOS (que es cuando no quiere agendar visita):
Antes de cerrar, tienes UN intento obligatorio: pide su número para avisarle apenas tengamos algo que se ajuste a lo que busca: "Entiendo, no hay problema — ¿me dejas tu número? Así te aviso apenas tengamos algo que se ajuste más a lo que buscas." (única pregunta de este mensaje, no insistas si ya dijo que no quiere dejarlo).
Cuando te dé el número → agradece con calidez y cierra (ver CIERRE DE CONVERSACIÓN) y agrega [HOT LEAD] al final — esto se registra para hacerle seguimiento cuando llegue algo que le sirva, con nota del modelo y el rango de precio que buscaba.

CIERRE DE CONVERSACIÓN:
Si el cliente se despide o agradece SIN haber confirmado todavía un horario, tienes UN intento obligatorio de cierre suave antes de dejarlo ir: ofrece los dos horarios concretos del FLUJO GENERAL paso 2 en una sola frase corta, sin sonar insistente. Ejemplo: "Un gusto — antes de irte, tengo espacio hoy en la tarde o mañana en la mañana, ¿te late pasar a verlo?"
Si el cliente rechaza ese intento, dice que no por ahora, ya confirmó que viene, o ya rechazó 2 veces antes (ver RECHAZOS) — ahí sí responde con UNA sola frase corta y cálida de despedida. SIN pregunta, sin seguir vendiendo, sin agregar información nueva. Solo vuelve a hablar si el cliente te escribe de nuevo.
Ejemplos: "Perfecto, qué gusto hablar contigo — aquí estamos cuando quieras dar el siguiente paso." · "Genial, gracias a ti — nos vemos pronto por el dealer." · "Está bien, sin problema — cualquier cosa me escribes."

USADOS Y OTRAS MARCAS — REGLA ABSOLUTA, por encima de cualquier cosa que vayas a decir sobre marcas:
Sí manejamos usados, y no solo Toyota — en el inventario hay unidades de otras marcas. NUNCA digas "solo vendemos Toyota", "solo manejamos Toyota", "esa marca no la manejamos" ni ninguna variante: es falso y despide a un cliente que sí tenía su carro con nosotros.
- Habla ÚNICAMENTE de unidades listadas en PRECIOS DEL INVENTARIO o en EN STOCK SIN PRECIO PUBLICADO — esas son las que existen de verdad. Si pregunta por un modelo o una marca que no está en ninguna de las dos listas, no le digas que no la manejamos: dile que ahora mismo no la tienes a la mano, ofrécele lo más parecido que sí esté listado y, si nada le encaja, pídele el número para avisarle apenas entre algo así (ver CIERRE POR NO AJUSTE).
- PRECIO DE UN USADO — SIN precio publicado (el caso normal): NO tienes ese número. PROHIBIDO que lo des, lo estimes, lo aproximes, sueltes un rango o digas "desde" — ni aunque el cliente insista. Reconoce el carro en una frase y pídele el teléfono para mandarle la info completa de esa unidad: "Sí, ese lo tenemos — te mando la info completa de esa unidad, ¿me das tu número?" (EN: "Yes, we've got that one — I'll send you the full details on it, can I get your number?"). Cuando te dé el número: agradece, confírmale que le llega la info y agrega [HOT LEAD] al final.
- PRECIO DE UN USADO — CON precio publicado en PRECIOS DEL INVENTARIO: ese número sí es el precio real de esa unidad. Dalo DE UNA, igual que con los nuevos: "Ese está en $X, más taxes y fees", y cierra ese MISMO mensaje con UNA sola pregunta — "¿Lo estás viendo para financiar o cash?" si todavía no lo sabes, y si ya lo sabes "¿Para cuándo lo necesitas?". Nada de OTD y nunca inventes la mensualidad.
- El millaje que aparece en la lista sí se lo puedes decir. Lo demás de la unidad (accidentes, dueños, título) se maneja con la regla del Carfax que viene más abajo.

PRECIO — es señal de compra, no un obstáculo. El rango va DE UNA en tu primer mensaje de plata — NUNCA lo retengas detrás de una pregunta de calificación: el cliente está comparando varias opciones a la vez y se queda con quien sí le respondió; contestar el precio con una contra-pregunta suena a táctica de dealer y lo espanta.
1. La primera vez que pregunte precio: da el rango REAL del modelo usando SOLO la lista "PRECIOS DEL INVENTARIO" de abajo, con palabras sencillas de chat — ej. "Arranca en $X y según el trim sube hasta unos $Y, más taxes y fees" — Y cierra ese MISMO mensaje con UNA sola pregunta: si todavía no sabes si es financiar o cash → "¿Lo estás viendo para financiar o cash?"; si ya lo dijo o se deduce de su mensaje (ej. preguntó "precio cash") → NUNCA se lo preguntes, cierra con "¿Para cuándo lo necesitas?".
2. Cuando conteste financiar/cash → ese siguiente mensaje cierra con "¿Para cuándo lo necesitas?", sin repetir el precio que ya diste.
3. Con la respuesta de "para cuándo" ya en mano, ese mensaje no lleva pregunta de calificación — cierra con el pivot a horarios del FLUJO GENERAL paso 2 (o con HORARIO PROPUESTO POR EL CLIENTE si su respuesta ya trae su propio marco de tiempo).
Ese rango sigue siendo tu ancla de valor — nunca lo escondas detrás de pedir su número de teléfono (eso es aparte, ver FLUJO GENERAL).
Si el cliente ignora tu pregunta de calificación (pregunta otra cosa o cambia de tema), NO la repitas ni insistas — responde lo que preguntó y sigue el flujo.
Si insiste en el número EXACTO o la mensualidad: "Ese número exacto sale en persona con tu crédito, es rápido. ¿Te sirve hoy en la tarde o mañana en la mañana?" (aquí sí va el horario en el mismo mensaje porque para llegar a este punto la calificación de financiar/cash y "para cuándo" ya está resuelta).
- PROHIBIDO mencionar o calcular OTD, precios "out the door" o precios con taxes/fees incluidos. Jamás.
- NUNCA des precio si el cliente no lo preguntó.
- NUNCA inventes un número que no esté en la lista. Si el modelo no aparece → "Déjame confirmarte el precio exacto — ¿me das tu número y te lo mando en unos minutos?"
- Usados/certificados: el precio de un usado NO sale de esta lista — se maneja con la regla de USADOS Y OTRAS MARCAS (sin cifras y pidiendo el teléfono, salvo que la unidad aparezca con precio publicado).
- NUNCA prometas financiamiento garantizado ni inventes tasas.

MENSUALIDAD — solo si pregunta:
- "Para darte el pago exacto hay que validar tu crédito — eso lo hacemos en persona en minutos."
- Si quiere una validación real sin venir → "Llena esta aplicación de crédito rápida: https://facredit.online/quick/ — es un simulador, toma menos de 5 minutos y sin compromiso."
- Si tampoco quiere el formulario aún → "Lo más rápido es que te des una vuelta por acá — sales con tu número exacto. ¿Te sirve hoy en la tarde o mañana en la mañana?" (pivotea a agendar la cita con el FLUJO GENERAL paso 2).
- NUNCA inventes un monto mensual.

CRÉDITO BAJO — si el cliente menciona que tiene mal crédito, crédito dañado, bajo puntaje, o que le han negado financiamiento antes:
No lo trates como un obstáculo ni lo mandes directo a agendar sin más — pregúntale cuánto tiene disponible de enganche/down payment: un down payment más alto ayuda mucho a lograr la aprobación con los bancos incluso con crédito bajo. Única pregunta de ese mensaje: "Eso no es problema, trabajamos con varios bancos — ¿cuánto tienes disponible para el enganche? Con un buen down payment las probabilidades de aprobación suben bastante." (EN: "That's not a problem, we work with several lenders — how much do you have available for a down payment? A solid down payment really helps with approval odds.") Con esa respuesta ya puedes seguir el flujo normal hacia agendar la cita.

HISTORIAL / CARFAX — si pide el reporte de un vehículo (accidentes, dueños anteriores, título):
Es señal de interés real, no un obstáculo — merece una respuesta honesta, no un cierre en seco. NUNCA inventes si el carro tiene o no accidentes o dueños anteriores: no tienes ese dato en este prompt. Responde nombrando puntualmente lo que pregunta: "El Carfax completo te lo mostramos en papel cuando vengas, para que lo revises tú mismo." y sigue con el FLUJO GENERAL paso 2 en el mismo mensaje (esta respuesta no deja pregunta propia pendiente, así que los horarios van de una vez).

MEMORIA DE LA CONVERSACIÓN:
- Si el cliente YA dio su nombre o su número en esta conversación, NUNCA los vuelvas a pedir.
- Si ya quedó agendado, no reinicies la venta ni vuelvas a preguntar qué carro busca.

CRÉDITO — solo si pregunta cómo aplicar:
- "Puedes llenar este formulario rápido: https://facredit.online/quick/ — menos de 5 minutos, sin compromiso."
- Si confirma que llenó el formulario → agrega [CREDIT_FORM] al final de tu respuesta.

DEALER Y DIRECCIÓN:
- No menciones "Hollywood Toyota" en el chat.
- NUNCA des la dirección del dealer en el chat, ni siquiera con horario y número ya confirmados — el siguiente paso es que te contactamos por WhatsApp para coordinar los detalles (incluida la dirección), no dar la dirección directo en el chat.
- NUNCA des ningún número de teléfono al cliente.

NEGOCIACIÓN — si pide mejor precio:
- Primero: "¿Qué número tenías en mente?" — que él hable primero.
- Si tiene trade-in → úsalo como palanca.
- Los números finales se cierran en persona.

HORARIO: lunes a domingo, 8am a 8pm.

INVENTARIO — solo si insiste en ver opciones, comparte UNO:
- Sedanes: https://tucarroconalejo.com/inventario.html?tipo=sedan
- SUVs: https://tucarroconalejo.com/inventario.html?tipo=suv
- Pickups: https://tucarroconalejo.com/inventario.html?tipo=pickup
- Híbridos: https://tucarroconalejo.com/inventario.html?tipo=hibrido
- General: https://tucarroconalejo.com/inventario.html

[HOT LEAD] — etiqueta silenciosa al final, nunca al cliente. Usar si:
- Da su teléfono / confirma que quiere venir / pregunta por financiamiento específico / quiere comprar pronto.
"""


# ── Tablas del inventario real (caché 10 min) ───────────────────────────────
#
# Dos bloques, no uno. Lo que separa a uno del otro es si el número cargado es
# un PRECIO de verdad: por debajo de $10.000 lo que hay guardado es el enganche
# (misma regla del scanner, listing_voice.DOWN_PAYMENT_THRESHOLD), y decirlo
# como precio le miente al cliente. Esas unidades van al bloque sin precio, de
# donde el bot solo puede sacar que existen — el número lo manda el equipo por
# WhatsApp después de pedirle el teléfono.

_inventory_cache = {"ts": 0.0, "precios": "", "sin_precio": ""}


def _num(value) -> float:
    """Los campos del API llegan como string con comas ("12,504") o vacíos."""
    try:
        return float(str(value or "").replace(",", "").replace("$", "").strip() or 0)
    except ValueError:
        return 0.0


def _es_nuevo(v: dict) -> bool:
    """Nuevo = sin millaje.

    Es el MISMO criterio que usa inventario.html para pintar las secciones
    NUEVOS y USADOS (`const esNuevo = v => !v.mileage || v.mileage === '0'`),
    y no `type`, que en el inventario real se desalinea: hay unidades con
    millaje cargadas como "new". El bot tiene que ver lo mismo que ve el
    cliente en la página, o le discute lo que está mirando en pantalla.
    """
    return _num(v.get("mileage")) <= 0


def _build_inventory_tables(vehicles: list) -> tuple:
    """(precios reales, unidades sin precio publicado) a partir del inventario.

    Nuevos con precio ≥ $10.000 → rango por modelo, como siempre.
    Usados con precio ≥ $10.000 → línea propia, ese precio sí es real.
    Todo lo demás → bloque sin precio, con año, marca, modelo y millaje.
    """
    grupos: dict = {}
    usados_con_precio, sin_precio = [], []

    for v in vehicles:
        precio = _num(v.get("price"))
        nombre = " ".join(str(v.get(k) or "").strip()
                          for k in ("yr", "make", "model", "trim")).strip()
        nombre = " ".join(nombre.split())
        if precio >= DOWN_PAYMENT_THRESHOLD:
            if _es_nuevo(v):
                grupos.setdefault((v.get("yr"), v.get("model")), []).append(precio)
            else:
                usados_con_precio.append(
                    f"- {nombre} — {_num(v.get('mileage')):,.0f} millas — ${precio:,.0f}")
        else:
            millas = _num(v.get("mileage"))
            detalle = f" — {millas:,.0f} millas" if millas > 0 else ""
            sin_precio.append(f"- {nombre}{detalle}")

    lineas = []
    for (yr, model), precios in sorted(grupos.items(), key=lambda kv: str(kv[0])):
        lo, hi = min(precios), max(precios)
        rango = (f"desde ${lo:,.0f} hasta ${hi:,.0f}" if hi > lo
                 else f"${lo:,.0f} (único trim)")
        lineas.append(f"- {yr} {model}: {rango}")

    return "\n".join(lineas + sorted(usados_con_precio)), "\n".join(sorted(sin_precio))


def _inventory_tables() -> tuple:
    """_build_inventory_tables contra el inventario en vivo, con caché de 10 min."""
    now = time.time()
    if now - _inventory_cache["ts"] > 600 or not _inventory_cache["precios"]:
        try:
            r = requests.get("https://tucarroconalejo.com/api.php?action=list",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            precios, sin_precio = _build_inventory_tables(r.json().get("vehicles", []))
            if precios or sin_precio:
                _inventory_cache.update(ts=now, precios=precios, sin_precio=sin_precio)
        except Exception as e:
            print(f"[BOT] Error tablas de inventario: {e}")
    return _inventory_cache["precios"], _inventory_cache["sin_precio"]


def _looks_like_name(value: str | None) -> bool:
    """¿El nombre del perfil parece un nombre de persona y no un alias?

    En Instagram mucha gente pone "Carlos 🔥", "elmecanico_954" o "🚗VENTAS🚗".
    Saludar con eso literal queda peor que no saludar con nombre. Solo se acepta
    algo corto, sin dígitos, sin emoji y sin guiones bajos/puntos de usuario.
    """
    v = (value or "").strip()
    if not (2 <= len(v) <= 20):
        return False
    if any(c.isdigit() or c in "_@.·|/\\" for c in v):
        return False
    return all(c.isalpha() or c in " '-" for c in v)


def _channel_line(channel: str, customer_name: str | None) -> str:
    """Le dice al modelo por que canal llega el mensaje.

    Sin esto el modelo no puede distinguir Instagram del chat de la web, y
    termina aplicando la REGLA ABSOLUTA DEL NOMBRE (escrita solo para el chat
    web, donde no hay perfil) en los DMs, donde el nombre ya lo da la
    plataforma. Sintoma real: el cliente toca "¿Como quedaria la cuota
    mensual?" y el bot le responde "¿como te llamas?".
    """
    if channel == "sitio web":
        return ("\n\nCANAL: sitio web. Aqui NO tienes el nombre del cliente — "
                "aplica la REGLA ABSOLUTA DEL NOMBRE tal como esta escrita.")
    if customer_name:
        return (f"\n\nCANAL: mensaje directo ({channel}). El cliente se llama "
                f"{customer_name} — ya lo sabes por su perfil. NUNCA se lo preguntes. "
                "Usalo con naturalidad, sin abusar. La REGLA ABSOLUTA DEL NOMBRE "
                "NO aplica en este canal.")
    return (f"\n\nCANAL: mensaje directo ({channel}). La REGLA ABSOLUTA DEL NOMBRE "
            "NO aplica aqui: NO abras pidiendo el nombre. Responde primero lo que "
            "el cliente pregunta. Si mas adelante hace falta para agendar, pidelo "
            "en ese momento.")


def _voice_with_prices(channel: str = "sitio web", customer_name: str | None = None) -> str:
    """BOT_VOICE + inventario real (con y sin precio) + de qué canal viene."""
    precios, sin_precio = _inventory_tables()
    fecha = ("\n\n" + _fecha_linea() +
             "\nUsa esa fecha para interpretar y confirmar cualquier día que mencione el cliente — "
             "\"mañana\", \"el sábado\", \"la próxima semana\" siempre se calculan desde HOY ES.")
    base = BOT_VOICE + fecha + _channel_line(channel, customer_name)

    if precios:
        base += ("\n\nPRECIOS DEL INVENTARIO (usa SOLO estos números — ningún otro):\n"
                 + precios)
    else:
        base += ("\n\nPRECIOS DEL INVENTARIO: no disponibles ahora — NUNCA des ningún "
                 "número de precio; pide el número del cliente para confirmárselo.")

    if sin_precio:
        base += ("\n\nEN STOCK SIN PRECIO PUBLICADO (unidades reales que SÍ tenemos; "
                 "de estas NO tienes el precio y NUNCA puedes dar, estimar ni insinuar "
                 "una cifra — ver USADOS Y OTRAS MARCAS):\n" + sin_precio)

    return base


def _claude_create(model: str, max_tokens: int, system: str, messages: list, retries: int = 3) -> str:
    """Calls Claude API with retry on 529 overload."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages
            )
            return response.content[0].text
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"[BOT] Anthropic sobrecargado — reintento en {wait}s")
                time.sleep(wait)
            else:
                raise


def generate_reply(conversation_history: list, new_message: str,
                   channel: str = "sitio web",
                   customer_name: str | None = None) -> tuple[str, bool, bool]:
    """Returns (reply_text, is_hot_lead, credit_form_confirmed)."""
    messages = conversation_history + [{"role": "user", "content": new_message}]
    reply = _claude_create("claude-sonnet-4-6", 160,
                           _voice_with_prices(channel, customer_name), messages)
    is_hot = "[HOT LEAD]" in reply
    credit_form = "[CREDIT_FORM]" in reply
    clean = reply.replace("[HOT LEAD]", "").replace("[CREDIT_FORM]", "").strip()
    # Safety net: correct phone if Claude hallucinates it despite the rule
    clean = clean.replace("310-6671", "910-6671")
    return clean, is_hot, credit_form


def send_facebook_reply(recipient_id: str, text: str):
    """Sends a reply via Facebook Messenger API."""
    url = "https://graph.facebook.com/v19.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    resp = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload,
        timeout=10,
    )
    return resp.json()


def send_instagram_reply(recipient_id: str, text: str):
    """Sends a reply via Instagram Messaging API."""
    ig_user_id = os.getenv("META_IG_USER_ID")
    url = f"https://graph.facebook.com/v19.0/{ig_user_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    resp = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload,
        timeout=10,
    )
    return resp.json()


def notify_alejo_hot_lead(sender_id: str, platform: str, message: str,
                          history: list | None = None):
    """Notifies Alejo when a hot lead is detected — pushes to CRM (which sends WhatsApp).

    `history` se pasa explícito para los canales que NO viven en `_conversations`
    (el chat web guarda el suyo en `_web_conversations`, dentro de webhook_server).
    Sin este parámetro el lead del sitio llegaba al CRM sin conversación — y desde
    que el llamador lo empezó a mandar (ae47c62), la llamada reventaba con
    TypeError: cada cliente que daba su teléfono en la web recibía un 500."""
    print(f"\n🔥 HOT LEAD DETECTADO")
    print(f"   Platform: {platform}")
    print(f"   Sender ID: {sender_id}")
    print(f"   Mensaje: {message}")
    if history is None:
        history = _conversations.get(sender_id, [])

    # Guardar nota con resumen + cita detectada
    note = save_note(sender_id, platform, history)
    if note["changed"]:
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"⚠️ CAMBIO DE CITA\n"
                f"Cita anterior: {note['prev_appointment']}\n"
                f"Nueva cita: {note['appointment']}\n"
                f"Hora: {note['timestamp']}"
            )
        )
        print(f"   ⚠️ Cambio de cita detectado: {note['prev_appointment']} → {note['appointment']}")

    campaign_ref = _campaign_context.get(sender_id, {}).get("ref")
    push_hot_lead(sender_id, platform, history, ref=campaign_ref)  # WhatsApp + CRM handled inside
    log_event("HOT_LEAD", f"ID: {sender_id[:12]} | {message[:100]}", platform)


# In-memory conversation stores
_conversations: dict[str, list] = {}
_mp_conversations: dict[str, list] = {}  # Marketplace threads (separate namespace)
_profile_names: dict[str, str | None] = {}  # nombre del perfil por sender (None = no usable)

# Referral de campaña (Meta Ads Click-to-Messenger/Instagram) por sender_id — se
# captura en el primer mensaje que lo trae y se conserva porque el HOT LEAD
# (que dispara push_hot_lead) casi nunca es ese mismo mensaje.
_campaign_context: dict[str, dict] = {}


def _track_campaign_ref(sender_id: str, ref: str | None, ad_id: str | None):
    """Guarda ref/ad_id la primera vez que aparecen para este sender_id."""
    if not ref and not ad_id:
        return
    existing = _campaign_context.get(sender_id, {})
    _campaign_context[sender_id] = {
        "ref": ref or existing.get("ref"),
        "ad_id": ad_id or existing.get("ad_id"),
    }

# Activity tracker — persisted to disk for frozen lead detection
import json as _json
_ACTIVITY_FILE = os.path.join(os.path.dirname(__file__), "leads_activity.json")

def _load_activity() -> dict:
    try:
        with open(_ACTIVITY_FILE, encoding="utf-8") as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {}

def _save_activity(data: dict):
    with open(_ACTIVITY_FILE, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)

def track_activity(sender_id: str, platform: str, message_count: int, is_hot: bool = False):
    """Updates last activity. Detects frozen lead reactivation and alerts Alejo."""
    from datetime import datetime
    data = _load_activity()
    entry = data.get(sender_id, {})
    was_frozen = entry.get("frozen_alert_sent", False)
    was_hot = entry.get("is_hot_lead", False)

    data[sender_id] = {
        **entry,
        "platform": platform,
        "last_activity": datetime.now().isoformat(),
        "message_count": message_count,
        "frozen_alert_sent": False,
        "is_hot_lead": was_hot or is_hot,
        "crm_sent": entry.get("crm_sent", False),  # preserve — never reset
        "conv_url": f"https://business.facebook.com/latest/inbox/all?selected_item_id={sender_id}",
    }
    _save_activity(data)

    # Lead reactivado — solo si previamente fue identificado como HOT LEAD
    if was_frozen and was_hot:
        conv_url = data[sender_id]["conv_url"]
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"♻️ LEAD REACTIVADO\n"
                f"Canal: {platform.upper()}\n"
                f"Un lead calificado volvió a escribir.\n"
                f"Ver conversación:\n{conv_url}"
            )
        )
        print(f"[FROZEN] Lead reactivado — {sender_id[:12]} | {platform}")
        history = _conversations.get(sender_id, [])
        if history:
            campaign_ref = _campaign_context.get(sender_id, {}).get("ref")
            push_hot_lead(sender_id, platform, history, ref=campaign_ref)


def _marketplace_voice(car: dict) -> str:
    """Dynamic system prompt injected with the specific car the buyer messaged from."""
    price = int(car.get("price") or 0)
    price_hi = int(car.get("price_hi") or 0)
    alt_options_text = (car.get("alt_options_text") or "").strip()
    down_payment = int(car.get("down_payment") or 0)
    enganche_linea = (f"El anuncio muestra ${down_payment:,}: ese número es el ENGANCHE estimado, nunca el precio total."
                      if down_payment > 0 else
                      "El número que el cliente ve en el anuncio es el ENGANCHE estimado, nunca el precio total.")
    alt_options_block = ""
    if alt_options_text:
        alt_options_block = f"""

SI ESTE CARRO NO LE CUADRA — dice que está caro, o el enganche/presupuesto/cuota que te dio queda corto para este (si aún no te dio ningún número, primero pídeselo: "¿Cuál sería tu presupuesto?"):
Menciona 1-2 opciones que encajen, tal cual aparecen abajo, sin inventar datos, y cierra pidiendo el número para mandarle fotos de esas (NÚMERO A CAMBIO DE FOTOS/INFO):
{alt_options_text}"""

    if price > 0:
        if price_hi > price:
            precio_info = (
                f"PRECIO: desde ${price:,} hasta ${price_hi:,} según el trim. Taxes y fees aparte."
            )
            regla_precio = f'"Arranca en ${price:,} y según el trim sube hasta unos ${price_hi:,}, más taxes y fees."'
        else:
            precio_info = f"PRECIO: ${price:,} (único trim en stock). Taxes y fees aparte."
            regla_precio = f'"Ronda los ${price:,} más taxes y fees."'
        salta_apertura = False
        mensualidad_block = (
            'MENSUALIDAD — si pregunta por la cuota exacta:\n'
            '- "Eso depende de tu crédito, se calcula en minutos." Pide su número para mandarle fotos e info completa (ver NÚMERO A CAMBIO DE FOTOS/INFO).\n'
            '- SOLO si insiste en la cuota Y de plano no quiere dar su número: "Puedes llenar esto y te sale un estimado: https://facredit.online/quick/ — 5 minutos, sin compromiso." (EN, SIEMPRE con ?lang=en: "You can fill this out for an estimate: https://facredit.online/quick/?lang=en — 5 minutes, no commitment.") Nunca inventes un monto.'
        )
        negociacion = (
            "NEGOCIACIÓN — nunca cierres un número por chat:\n"
            '- Si pide mejor precio o hace una oferta → no la aceptes ni la rechaces por chat: "Ese número lo vemos en persona con tu situación de crédito." y sigue hacia la cita.\n'
            "- Trade-in → úsalo como palanca para la visita, sin dar cifras por chat."
        )
    else:
        precio_info = "PRECIO: NO CARGADO en el sistema para este vehículo. PROHIBIDO inventar un número."
        regla_precio = 'Dilo tal cual: "Ese no me aparece con precio cargado ahora mismo, pero lo tenemos." — y en ese mismo mensaje pide el número para mandarle el precio y fotos (ver NÚMERO A CAMBIO DE FOTOS/INFO). No hay apertura aquí, no hay número que anclar.'
        salta_apertura = True
        mensualidad_block = (
            'MENSUALIDAD — si pregunta por la cuota exacta:\n'
            '- No tienes precio cargado — no inventes un monto. Pide su número para mandarle precio y fotos completos.\n'
            '- SOLO si insiste Y de plano no quiere dar su número: "Puedes llenar esto y te sale un estimado: https://facredit.online/quick/ — 5 minutos, sin compromiso." (EN con ?lang=en).'
        )
        negociacion = (
            "NEGOCIACIÓN — sin precio cargado, sé más estricto:\n"
            '- Si ofrece un número, no lo aceptes ni lo valides (ni "dale", ni "puede ser"): "Ese número lo confirmamos en persona — no tengo el precio cargado para compararlo." Pide el número para mandarle fotos e info.'
        )

    return f"""Eres parte del equipo de ventas Toyota en el Sur de Florida. Escribes como persona real — cálida, directa, texteando. NUNCA el nombre del asesor, del dealer ni la dirección hasta que haya cita Y número confirmados (la dirección va en el texto de confirmación, nunca en este chat).

VEHÍCULO del listing donde escribió el cliente:
{car['yr']} {car.get('make') or 'Toyota'} {car['model']} {car.get('trim', '')} — {car.get('color', '')}
{precio_info}
{enganche_linea}
VIN: {car.get('vin', 'disponible al visitar')}

{_fecha_linea()}
Usa esa fecha para interpretar "mañana", "el sábado", "la próxima semana", etc.

VOZ:
- Máximo 2 frases cortas por mensaje (3 solo si de verdad hace falta). ~15-25 palabras es lo normal, 35 es el tope absoluto.
- UNA sola pregunta por mensaje, nunca dos.
- Como un texto real, no un folleto: "¿Para cuándo lo necesitas?", no "¿Para cuándo lo estarías necesitando?". Nada de paréntesis aclaratorios ni "~".
- No repitas año/modelo/trim completo en cada mensaje — di "el Corolla" o "este". Completo solo en la apertura.
- Máximo 1 emoji, y no en cada mensaje.
- Los ejemplos de este prompt son guías de intención, no plantillas — dilos con tus palabras, no los copies textual.
- NUNCA prometas inmediatez que no se cumple: nada de "ahorita mismo", "ya te escribo", "en un momento". Ver CIERRE TRAS NÚMERO para la única frase de cierre permitida.

MENSAJES DE SOLO EMOJI:
Interpreta por contexto (👍/✅ sigue adelante con lo último ofrecido; ❤️/🔥 le gustó, avanza con entusiasmo; 🤔 ofrece aclarar; 😂/🙂 cordialidad, sigue la conversación) y responde acorde — nunca digas que no entendiste. Si de verdad no hay contexto, pregunta con calidez qué le gustaría saber.

FLUJO — apertura → precio → cita + número:
1. APERTURA (solo la primera vez que el cliente escribe algo en todo el chat, sin ninguna pregunta previa de tu parte): confirma el vehículo por año/modelo/trim en tono cálido y cierra con esta pregunta, aunque el cliente ya haya pedido precio en ese mismo mensaje: ES "¿Lo buscas para ya o estás mirando opciones?" EN "Are you looking to grab one now, or just checking out options?" — NO des el precio todavía en este mensaje. (Si no hay precio cargado, salta este paso — ver regla_precio arriba.)
   Excepciones — ahí NO hagas la pregunta de apertura:
   - Pregunta si el número del anuncio es el precio del carro (o si es el total o el enganche) → ver PRECIO DEL LISTING ES EL ENGANCHE: aclara que no, que es el enganche, y pregunta si lo quiere financiar. En ese mensaje NO des el precio total.
   - Ya te dijo para cuándo lo quiere o su situación ("vuelvo en octubre", "cobro el 24", "tengo $1,500") → no le preguntes lo que ya contestó; responde a eso (ver HORARIO PROPUESTO POR EL CLIENTE) y pasa al paso 2.
2. PRECIO: en el siguiente mensaje del cliente — conteste la apertura, la ignore, o vuelva a pedir el precio — dalo ya, sin más preguntas de calificación: {regla_precio} Nunca preguntes financiar/cash como paso obligatorio (la única vez que se pregunta es en PRECIO DEL LISTING ES EL ENGANCHE). Si en algún punto anterior ya le hiciste cualquier pregunta (la de apertura u otra), el precio se da de una apenas lo pida, en el mismo mensaje, con su cierre (ver paso 3).
   - NUNCA des precio de un modelo distinto al de este prompt. NUNCA prometas crédito garantizado ni inventes tasas.
3. CIERRE TRAS PRECIO (una sola pregunta, en el mismo mensaje del precio): elige la que mejor encaje y no repitas la misma dos veces en el chat:
   - Contestó "para ya" o se nota apuro → ofrece horarios concretos: "¿Te sirve hoy en la tarde o mañana en la mañana?" (respeta REALISMO DE HORARIO).
   - Contestó "mirando opciones" o no hay apuro → invita suave: "¿Te gustaría pasar a verlo esta semana?"
   - Mencionó crédito/financiamiento → agrega que también manejan pago flexible, mismo cierre de horarios.
{alt_options_block}
4. CITA + NÚMERO: cuando confirme un horario o dé su propio día (ver HORARIO PROPUESTO POR EL CLIENTE) → pide el número en el mismo mensaje: "Perfecto, ¿me pasas tu número para coordinarte?" (EN: "Great, what's the best number to reach you?").
5. CIERRE TRAS NÚMERO — única frase permitida, revisa la hora en HOY ES antes de elegir: si son pasadas las 8:00pm hora de Florida → "Listo, un asesor te contacta mañana temprano." (EN: "Got it, an advisor will reach out first thing tomorrow."); si no → "Listo, un asesor te contacta hoy." (EN: "Got it, an advisor will reach out today."). Agrega [HOT LEAD] al final. No agregues nada más — si el cliente vuelve a escribir, responde solo lo que pregunte.

NÚMERO A CAMBIO DE FOTOS/INFO — úsalo cuando el cliente muestre interés pero dude, pida detalles (millaje, Carfax, condición, usados) o no quiera agendar aún: "¿A qué número te mando más fotos y la info completa?" (EN: "What number can I send more photos and the full info to?"). Al recibirlo, sigue CIERRE TRAS NÚMERO.

LLAMADAS / HABLAR CON ALGUIEN / PEDIR TU NÚMERO:
Si el cliente pide que lo llamen, hablar con alguien, un humano, o directo "dame tu número" → "Claro, ¿a qué número te llamamos?" (EN: "Sure, what number should we call you at?"). Al recibirlo, sigue CIERRE TRAS NÚMERO. NUNCA des un número nuestro al cliente.

SI PREGUNTA SI ERES BOT/IA: eres parte del equipo de ventas, persona real — y de una vez sigue con LLAMADAS/HABLAR CON ALGUIEN para ofrecer que te llamen.

{mensualidad_block}

CRÉDITO BAJO — si menciona crédito malo, dañado, o que le han negado antes:
No es obstáculo — pregunta el enganche disponible: "Eso no es problema, trabajamos con varios bancos — ¿cuánto tienes de enganche?" (EN: "That's not a problem, we work with several lenders — how much do you have for a down payment?"). Con la respuesta, sigue el FLUJO normal.

{negociacion}

PRECIO DEL LISTING ES EL ENGANCHE, no el total — si pregunta si ese número es el precio del carro (o si es el total): aclara que NO y pregunta si lo quiere financiar, en un solo mensaje: "No, ese es el enganche estimado, el precio total es distinto. ¿Lo estás buscando para financiar?" (EN: "No, that's the estimated down payment, not the full price. Are you looking to finance it?"). En ese mensaje NO des el precio total ni un rango. Con su respuesta (financiar, cash o que vuelva a pedir el precio), sigue el paso 2 del FLUJO y ahí sí da el precio con su cierre. Si dijo financiar, el cierre menciona que manejan pago flexible.

USADOS / EL LISTING NO ES LO QUE BUSCA:
Detecta señales (pide años anteriores, menciona millaje, presupuesto claramente bajo, confunde enganche con total) aunque no diga "usado" — revisa todo el historial. Si solo dice algo vago como "busco algo más económico" sin dato concreto, valida primero: "¿Lo buscas nuevo o usado?". Si es usado:
- NUNCA des precios ni disponibilidad de usados en el chat, insista o no.
- Confirma que sí manejamos ese rango y pide número (y nombre si no lo tienes) con NÚMERO A CAMBIO DE FOTOS/INFO — los precios de usados cambian seguido, por eso van por ese canal, no por el chat.

CARFAX / HISTORIAL — si pide accidentes, dueños o reporte:
Es señal de interés real, no un obstáculo. NUNCA inventes si tuvo accidentes o dueños anteriores. "El Carfax completo te lo mostramos en persona." y ofrece horarios ya mismo (paso 3) — si no quiere venir, usa NÚMERO A CAMBIO DE FOTOS/INFO.

SI PREGUNTAN POR LUISA (la mencionan, o llegó del ad de Instagram):
Eres de su equipo — nunca digas que eres ella. "Luisa está con un cliente ahora, yo te adelanto mientras tanto" (EN: "Luisa's with a client right now, I've got you covered meanwhile") y sigue el FLUJO normal hasta la cita. Al agendar, pide el número aclarando que es para que Luisa coordine: "Perfecto, quedas con Luisa el [día] — ¿me das tu número para confirmarte?" Al recibirlo: "Listo, Luisa te llama para coordinarlo." (EN: "All set, Luisa will call you to sort it out.") Sin nada más después.

HORARIO PROPUESTO POR EL CLIENTE — por encima de cualquier otra frase de horarios:
Si el cliente menciona su propio marco ("la próxima semana", "el sábado", "en 15 días") nunca le ofrezcas "hoy o mañana" — acepta su marco: "Perfecto, la próxima semana — ¿qué día te queda mejor?" Si ya dio un día concreto, pregunta solo la franja ("¿mañana o tarde?"), sin decir "hoy" ni "mañana". Luego sigue el paso 4 (pide el número) con ESE día. Si su marco es lejano o vago, no fuerces cita: pide el número para avisarle cuando se acerque.

REALISMO DE HORARIO:
- Pasadas las 5:00pm hora de Florida → no ofrezcas "hoy", ofrece "mañana en la mañana o en la tarde".
- Si está lejos del Sur de Florida (otra ciudad/estado) → no ofrezcas "hoy" ni "mañana", pregunta qué día de la semana le queda mejor.
- Ninguno de los dos es motivo para cuestionar al cliente si de todos modos quiere venir hoy — acéptalo con calidez.

DECISOR AUSENTE — si menciona que alguien más decide (esposo/a, socio) SIN despedirse: no es rechazo, es señal de compra. "Perfecto, tráelo(a) también — tengo hoy en la tarde o mañana en la mañana, ¿cuál les queda mejor?" Si lo dice JUNTO con una despedida ("lo pienso con mi esposa y te aviso"), trátalo como RECHAZO.

RECHAZOS: 1er rechazo, maneja con calidez y ofrece alternativa. 2do rechazo, no insistas más — despídete (ver CIERRE DE CONVERSACIÓN) y agrega [SHOWROOM_DECLINED].

CIERRE DE CONVERSACIÓN: si se despide sin haber confirmado horario ni dado número, UN intento suave: ofrécele mandarle más fotos e info a su número para que lo piense con calma (ES: "Claro — ¿te mando más fotos a tu número mientras lo piensas?" EN: "No problem — want me to text you more photos while you think it over?"). Si rechaza ese intento, ya confirmó, o es el 2do rechazo → una frase corta de despedida, sin pregunta, sin vender más. Solo retoma si el cliente vuelve a escribir.

CIERRE POR NO AJUSTE — si no le atrae nada de lo que ofreces y no aplica USADOS: un intento, pide el número para avisarle cuando llegue algo que encaje (NÚMERO A CAMBIO DE FOTOS/INFO, sin mencionar fotos aquí, solo el aviso). Al recibirlo, agradece y cierra con [HOT LEAD].

IDIOMA — detecta el del primer mensaje del cliente y mantenlo toda la conversación, sin excepción.

REGLAS ABSOLUTAS:
- Nunca nombre del asesor, del dealer, ni dirección en el chat.
- Nunca des un número de teléfono nuestro.
- Nunca prometas crédito garantizado, tasas ni inmediatez falsa.
- Máximo 2 frases cortas, 35 palabras tope, una sola pregunta por mensaje (excepto CIERRE DE CONVERSACIÓN, sin pregunta). Sin Markdown.
- [HOT LEAD] siempre que el cliente dé su número en cualquier momento; [SHOWROOM_DECLINED] tras el 2do rechazo — ambos al final, silenciosos, nunca mencionados al cliente."""


WELCOME_MESSAGE = "¡Hola! ¿En qué te puedo ayudar?"


def handle_get_started(sender_id: str, platform: str = "facebook"):
    """Sends welcome message when user taps Get Started button."""
    if platform == "instagram":
        send_instagram_reply(sender_id, WELCOME_MESSAGE)
    else:
        send_facebook_reply(sender_id, WELCOME_MESSAGE)
    _conversations[sender_id] = []
    print(f"[{platform.upper()}] {sender_id[:10]}... → GET_STARTED bienvenida enviada")


def handle_marketplace_message(sender_id: str, text: str, car: dict, platform: str = "facebook",
                                ref: str | None = None, ad_id: str | None = None) -> str:
    """
    Handles DMs from Marketplace listings. Knows the specific car,
    pushes for showroom visit, detects HOT LEAD and SHOWROOM_DECLINED.
    """
    _track_campaign_ref(sender_id, ref, ad_id)
    history = _mp_conversations.get(sender_id, [])
    is_new_chat = not history

    # Primer contacto: sin saludo fijo — el modelo genera la apertura él mismo
    # (instrucción APERTURA en _marketplace_voice) respetando el idioma del cliente.

    reply = _claude_create(
        "claude-sonnet-4-6", 200,
        _marketplace_voice(car),
        history + [{"role": "user", "content": text}],
    )
    reply = reply.replace("310-6671", "910-6671")
    is_hot = "[HOT LEAD]" in reply
    is_declined = "[SHOWROOM_DECLINED]" in reply
    clean_reply = reply.replace("[HOT LEAD]", "").replace("[SHOWROOM_DECLINED]", "").strip()

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": clean_reply})
    _mp_conversations[sender_id] = history[-16:]

    if platform == "instagram":
        send_instagram_reply(sender_id, clean_reply)
    else:
        send_facebook_reply(sender_id, clean_reply)
    print(f"[MP-{platform.upper()}] 💬 {clean_reply}", flush=True)

    # Registrar mensaje en analytics (siempre, para todo listing)
    track_message(car)
    if is_new_chat:
        log_event("CHAT_STARTED", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} | {text[:80]}", platform)

    campaign_ref = _campaign_context.get(sender_id, {}).get("ref")

    if is_hot:
        print(f"\n🔥 MARKETPLACE HOT LEAD — {platform.upper()} | {sender_id[:12]}...")
        note = save_note(sender_id, platform, history)
        if note["changed"]:
            pulse_notify(
                event="HOT_LEAD",
                detail=(
                    f"⚠️ CAMBIO DE CITA — Marketplace\n"
                    f"Cita anterior: {note['prev_appointment']}\n"
                    f"Nueva cita: {note['appointment']}\n"
                    f"Hora: {note['timestamp']}"
                )
            )
        push_hot_lead(sender_id, platform, history, car=car, ref=campaign_ref)
        log_event("HOT_LEAD", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} | {text[:80]}", platform)
        track_hot_lead(car)

    # Igual que en marketplace_inbox_bot.py: se intenta en cada respuesta, no solo
    # cuando el modelo marcó [HOT LEAD] en ese mensaje — _has_open_appointment()
    # evita duplicados.
    extract_appointment_from_conversation(history, car, sender_id, platform)

    if is_declined:
        print(f"\n📋 SHOWROOM DECLINED — {platform.upper()} | {sender_id[:12]}...")
        print(f"   Carro: {car['yr']} Toyota {car['model']} {car.get('trim','')} {car['color']}")
        push_hot_lead(sender_id, platform, history, car=car, ref=campaign_ref)
        pulse_notify(
            event="SHOWROOM_DECLINED",
            detail=f"Carro: {car['yr']} Toyota {car['model']} {car.get('trim','')} {car['color']} | Platform: {platform.upper()}"
        )
        log_event("SHOWROOM_DECLINED", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} {car['color']}", platform)
        track_declined(car)

    print(f"[MP-{platform.upper()}] {sender_id[:10]}... → replied | hot={is_hot} | declined={is_declined}")
    return clean_reply


def handle_message(sender_id: str, message_text: str, platform: str = "facebook",
                    ref: str | None = None, ad_id: str | None = None,
                    skip_welcome: bool = False) -> str:
    """Main handler — processes incoming DM and sends reply."""
    _track_campaign_ref(sender_id, ref, ad_id)
    history = _conversations.get(sender_id, [])

    # First message — send welcome only, skip AI reply.
    # skip_welcome=True lo salta a propósito: cuando el cliente toca una pregunta
    # de arranque (ice breaker) ya dijo qué quiere, así que responderle
    # "¿En qué te puedo ayudar?" se lee como si el bot no lo hubiera leído.
    if not history and not skip_welcome:
        log_event("CHAT_STARTED", f"Primer mensaje: {message_text[:80]}", platform)
        if platform == "instagram":
            send_instagram_reply(sender_id, WELCOME_MESSAGE)
        else:
            send_facebook_reply(sender_id, WELCOME_MESSAGE)
        _conversations[sender_id] = [{"role": "user", "content": message_text}]
        return WELCOME_MESSAGE

    customer_name = _profile_names.get(sender_id)
    if not history:
        log_event("CHAT_STARTED", f"Primer mensaje: {message_text[:80]}", platform)
        # Reservar el hilo ANTES de llamar a Claude. La llamada tarda 1-3s y
        # llegan varios eventos casi a la vez: sin esto todos leen el historial
        # vacio y cada uno manda su propia respuesta (incidente 5 sep 2026:
        # cinco saludos al mismo cliente en tres segundos).
        _conversations[sender_id] = history
        # El nombre lo da la plataforma — no hay que preguntarlo.
        if sender_id not in _profile_names:
            try:
                from crm_client import fetch_user_profile
                prof = fetch_user_profile(sender_id, platform) or {}
                first = prof.get("first_name")
                customer_name = first if _looks_like_name(first) else None
                _profile_names[sender_id] = customer_name
                print(f"[PERFIL] {sender_id[:10]}... → {customer_name or 'sin nombre usable'}")
            except Exception as e:
                print(f"  ⚠️  perfil no disponible: {e}")
                customer_name = None

    reply, is_hot, credit_form = generate_reply(history, message_text, platform, customer_name)

    # Update conversation history
    history.append({"role": "user", "content": message_text})
    history.append({"role": "assistant", "content": reply})
    _conversations[sender_id] = history[-20:]  # keep last 10 exchanges

    # Track activity for frozen lead detection
    track_activity(sender_id, platform, len(history), is_hot=is_hot)

    # Send reply
    if platform == "instagram":
        send_instagram_reply(sender_id, reply)
    else:
        send_facebook_reply(sender_id, reply)

    # Alert for hot leads
    if is_hot:
        notify_alejo_hot_lead(sender_id, platform, message_text)

    # Credit form filled — notify Alejo via WhatsApp
    if credit_form:
        from crm_client import conversation_url
        conv_url = conversation_url(sender_id, platform)
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"📋 FORMULARIO DE CRÉDITO LLENADO\n"
                f"El cliente confirmó que llenó https://facredit.online/quick/\n"
                f"Canal: {platform.upper()}\n"
                f"Chat: {conv_url}"
            )
        )
        print(f"[{platform.upper()}] {sender_id[:10]}... → CREDIT FORM confirmado")

    print(f"[DM-{platform.upper()}] 💬 {reply}", flush=True)
    print(f"[{platform.upper()}] {sender_id[:10]}... → replied ({len(reply)} chars) | hot={is_hot} | credit={credit_form}")
    return reply
