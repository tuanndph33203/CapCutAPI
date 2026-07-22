/**
 * List ASR models: R2 keys under prefix "asr/" → unique model names (first path segment).
 * Production only; local dev uses Vite middleware that lists public/asr-model/ subdirs.
 */
export async function onRequestGet(context: {
  env: { piper: R2Bucket };
}): Promise<Response> {
  try {
    const { env } = context;
    const prefix = 'asr/';
    const list = await env.piper.list({ prefix, delimiter: '/' });
    const models = (list.commonPrefixes || [])
      .map((p) => (p.replace(prefix, '').replace(/\/$/, '') || null))
      .filter(Boolean) as string[];
    return new Response(JSON.stringify({ models: [...new Set(models)].sort() }), {
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    });
  } catch (error) {
    console.error('Error listing ASR models:', error);
    return new Response(
      JSON.stringify({
        error: 'Failed to list ASR models',
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
