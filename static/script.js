// 移除了isPowerOn变量和电源开关按钮的逻辑

function sendCommand(direction) {
    // 直接发送命令，无需检查电源状态
    fetch(`/control`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({direction: direction})
    })
    .then(response => response.json())
    .then(data => console.log('Command Sent:', data))
    .catch(error => console.error('Error:', error));
}