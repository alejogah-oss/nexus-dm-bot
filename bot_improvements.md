# NEXUS Bot — Log de Mejoras

Agente responsable: **Pulse** (psicología del consumidor) + **Wire** (técnico)
Revisión: semanal — cada lunes

---

## Semana del 2026-06-25

### Cambios implementados

| # | Área | Cambio | Motivo |
|---|------|--------|--------|
| 1 | Flujo dirección | No dar dirección hasta confirmar día/hora | Bot entregaba dirección sin compromiso del cliente |
| 2 | Precio | Bot ahora da OTD real cuando cliente insiste | Evasión de precio estaba perdiendo leads |
| 3 | Precio | Primero califica con preguntas, precio como último recurso | Control de conversación antes de conceder |
| 4 | Precio | Desglose OTD: MSRP + taxes 7% + registro/fees $2,097 | Transparencia genera más confianza que evadir |
| 5 | Precio | Solo cotiza el carro exacto del listing — no estima otros trims | Riesgo de dar precios incorrectos |
| 6 | Dealer | No menciona "Hollywood Toyota" hasta que cliente da info | Evita resistencia prematura |
| 7 | Negociación | "¿Qué número tenías en mente?" antes de bajar precio | Cliente que pide mejor precio no siempre es por precio |
| 8 | Negociación | Trade-in como palanca antes de tocar precio del carro nuevo | Protege margen, cliente siente que ganó |
| 9 | Negociación | Si insiste → mover a mensualidad, no a OTD | Latinos piensan en pago mensual, no en total |
| 10 | CRM | Perfil psicológico del comprador incluido en nota CRM | Alejo llega preparado a la negociación |
| 11 | Leads | Alerta congelado/reactivado solo si tuvo señal HOT LEAD | Evita spam de notificaciones por conversaciones sin intención |

### Observaciones pendientes de validar
- [ ] ¿El desglose de OTD reduce objeciones de precio en visitas?
- [ ] ¿El perfil psicológico en el CRM le resulta útil a Alejo?
- [ ] ¿La pregunta "¿qué número tenías en mente?" genera más conversación o corta el hilo?

---

## Formato para próximas semanas

```
## Semana del [fecha]

### Señales observadas
- [patrón detectado en conversaciones]

### Cambios implementados
| # | Área | Cambio | Motivo |

### Resultados de la semana anterior
- [qué funcionó, qué no]

### Pendientes
- [ ] [acción]
```

---

## Reglas del proceso de mejora

1. **Ningún cambio se hace sin señal real** — debe haber una conversación o patrón que lo justifique.
2. **Un cambio a la vez por área** — no cambiar tono + precio + flujo al mismo tiempo.
3. **Validar antes de escalar** — si un cambio no mejora en 2 semanas, se revierte.
4. **Pulse analiza psicología** — Wire ejecuta los cambios técnicos.
