// Worker timers keep their pace while the dashboard tab is in the background.
onmessage=({data})=>setTimeout(()=>postMessage(data.id),data.ms);
