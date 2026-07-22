/**
 * Serve a single ASR model file from R2: key asr/{model}/{name}.
 */
export async function onRequestGet(context: {
  env: { piper: R2Bucket };
  params: { model: string; name: string };
}): Promise<Response> {
  try {
    const { env, params } = context;
    const model = params.model;
    const name = decodeURIComponent(params.name || '');
    if (!model || !name) {
      return new Response('Model and file name are required', { status: 400 });
    }
    const r2Key = `asr/${model}/${name}`;
    const object = await env.piper.get(r2Key);
    if (!object) {
      return new Response('Model file not found', { status: 404 });
    }
    let contentType = 'application/octet-stream';
    if (name.endsWith('.json')) contentType = 'application/json';
    if (name.endsWith('.js')) contentType = 'application/javascript';
    if (name.endsWith('.wasm')) contentType = 'application/wasm';
    return new Response(object.body, {
      headers: {
        'Content-Type': contentType,
        'Content-Length': object.size.toString(),
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  } catch (error) {
    console.error('Error serving ASR model file:', error);
    return new Response(
      JSON.stringify({
        error: 'Failed to serve model file',
        message: error instanceof Error ? error.message : String(error),
      }),
      {
        status: 500,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      }
    );
  }
}
