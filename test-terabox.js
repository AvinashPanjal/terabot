const TeraboxUploader = require('terabox-upload-tool');

async function test() {
  try {
    const uploader = new TeraboxUploader({ ndus: process.env.TERABOX_NDUS || '' });
    // Assuming it has a download method or similar. 
    console.log("Instance created. Prototypes:", Object.getOwnPropertyNames(TeraboxUploader.prototype));
  } catch(e) {
    console.error(e);
  }
}
test();
