import { useEffect, useRef } from "react"
import { getToken } from "./api"

export interface LiveEvent {
  type: "NEW_ALERT" | "ALERT_ACKNOWLEDGED"
  data: Record<string, unknown>
}

/** Subscribes to the live alert feed (backend/alerts/alert_manager.py) and
 * invokes onEvent for each message. Reconnects automatically on drop. */
export function useLiveFeed(onEvent: (event: LiveEvent) => void) {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    let socket: WebSocket | null = null
    let closedByCleanup = false
    let retryTimer: ReturnType<typeof setTimeout>

    function connect() {
      const token = getToken()
      if (!token) {
        // No token yet (e.g. right after logout, or a race with login) --
        // keep retrying on the same cadence as a dropped connection would,
        // otherwise this gives up silently and never reconnects even once a
        // token becomes available, since onclose never fires without a socket.
        retryTimer = setTimeout(connect, 2000)
        return
      }
      const protocol = window.location.protocol === "https:" ? "wss" : "ws"
      socket = new WebSocket(`${protocol}://${window.location.host}/api/alerts/ws?token=${encodeURIComponent(token)}`)
      socket.onmessage = (event) => {
        try {
          handlerRef.current(JSON.parse(event.data))
        } catch {
          /* ignore malformed message */
        }
      }
      socket.onclose = () => {
        if (!closedByCleanup) {
          retryTimer = setTimeout(connect, 2000)
        }
      }
    }

    connect()
    return () => {
      closedByCleanup = true
      clearTimeout(retryTimer)
      socket?.close()
    }
  }, [])
}
