const axios = require('axios');
async function test() {
  try {
    const res = await axios.get('https://terabox-dl.vkrdownloader.vercel.app/api?data=https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA', {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
    });
    console.log(res.data);
  } catch(e) {
    console.error(e.message);
  }
}
test();
