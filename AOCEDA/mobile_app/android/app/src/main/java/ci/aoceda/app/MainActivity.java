package ci.aoceda.app;

import android.Manifest;
import android.app.Activity;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.media.MediaRecorder;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.util.Base64;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Toast;
import com.getcapacitor.BridgeActivity;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Locale;
import org.json.JSONObject;

public class MainActivity extends BridgeActivity {
    private static final int REQ_NOTIF = 1001;
    private static final int REQ_STORAGE = 1002;
    private static final int REQ_AUDIO = 1003;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Demande de permission NOTIFICATIONS au démarrage (Android 13+/API 33), comme
        // une vraie app mobile — pour pouvoir alerter l'utilisateur en cas d'alerte
        // critique. Sur les versions antérieures, la permission est accordée d'office.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIF);
            }
        }
        // Écriture dans Téléchargements : requise seulement avant le stockage cadré
        // (API < 29) — au-delà, NativeDownloader passe par MediaStore, sans permission.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
            }
        }
        // Micro (dictée vocale de l'Assistant IA, NativeSpeech) : demandée au démarrage
        // pour que le bouton micro fonctionne dès le premier tap, sans coupure d'UX.
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_AUDIO);
        }

        WebView webView = getBridge().getWebView();
        WebSettings settings = webView.getSettings();

        // Rendu "application", pas "page web dans un navigateur" : pas de pincer-zoomer,
        // pas de loupe +/- native, pas de halo de rebond au bord de l'écran.
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);

        // L'alarme sonore d'alerte (Web Audio API, déclenchée par un polling en arrière-plan,
        // pas par un tap direct de l'utilisateur) doit pouvoir sonner sans geste préalable —
        // sinon la politique d'autoplay de la WebView la bloque silencieusement.
        settings.setMediaPlaybackRequiresUserGesture(false);

        // Stockage natif de session (SharedPreferences), INDÉPENDANT de l'origine
        // actuellement chargée dans la WebView — contrairement à localStorage, qui est
        // scopé par origine (http://<IP LAN>:<port>) et perd donc la session si l'IP du
        // PC change entre deux ouvertures de l'app (bail DHCP, changement de réseau…).
        // addJavascriptInterface() attache l'objet à la WebView elle-même, pas à une page
        // précise : il reste disponible après toute navigation, y compris vers le serveur
        // Django distant (contrairement au bridge JS propre de Capacitor, injecté
        // uniquement pour son origine locale). Utilisé UNIQUEMENT par static/js/auth.js
        // et client-shell.js quand l'app tourne dans ce wrapper natif — jamais sur le web.
        webView.addJavascriptInterface(new TokenStoreBridge(this), "AndroidTokenStore");

        // Téléchargement natif des exports (CSV/PDF) : les rapports exigent un jeton
        // Bearer (Authorization), donc le JS ne peut PAS se contenter d'une navigation
        // directe vers l'URL — il doit faire un fetch() + Blob. Or un Blob créé en
        // mémoire JS (URL.createObjectURL + <a download>) ne déclenche AUCUNE écriture
        // sur le disque dans une WebView Android nue (contrairement à un vrai navigateur
        // qui a sa propre intégration "Téléchargements") : le clic ne faisait donc rien.
        // Le JS convertit le Blob déjà récupéré en base64 et l'envoie ici, qui l'écrit
        // réellement dans le dossier Téléchargements (MediaStore sur API 29+, fichier
        // direct sinon). Voir client-shell.js → window.AOCEDA.downloadBlob().
        webView.addJavascriptInterface(new NativeDownloader(this), "NativeDownloader");

        // Dictée + lecture vocale de l'Assistant IA (page /ia/, static/js/ia.js) : la
        // WebView Android n'expose PAS l'API Web Speech du navigateur (SpeechRecognition,
        // speechSynthesis), il faut donc passer par les API natives Android équivalentes
        // (SpeechRecognizer, TextToSpeech) et renvoyer le résultat au JS via
        // evaluateJavascript(). Présence de window.NativeSpeech = détection côté JS.
        webView.addJavascriptInterface(new NativeSpeechBridge(this, webView), "NativeSpeech");
    }

    public static class TokenStoreBridge {
        private final SharedPreferences prefs;

        TokenStoreBridge(Context ctx) {
            prefs = ctx.getSharedPreferences("aoceda_session", Context.MODE_PRIVATE);
        }

        @JavascriptInterface
        public String getAccess() {
            return prefs.getString("access", "");
        }

        @JavascriptInterface
        public String getRefresh() {
            return prefs.getString("refresh", "");
        }

        @JavascriptInterface
        public String getRole() {
            return prefs.getString("role", "");
        }

        @JavascriptInterface
        public void save(String access, String refresh, String role) {
            prefs.edit()
                .putString("access", access == null ? "" : access)
                .putString("refresh", refresh == null ? "" : refresh)
                .putString("role", role == null ? "" : role)
                .apply();
        }

        @JavascriptInterface
        public void clear() {
            prefs.edit().clear().apply();
        }
    }

    public static class NativeDownloader {
        private final Activity activity;

        NativeDownloader(Activity activity) {
            this.activity = activity;
        }

        @JavascriptInterface
        public void saveBase64(String base64Data, String filename, String mimeType) {
            try {
                byte[] bytes = Base64.decode(base64Data, Base64.DEFAULT);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME, filename);
                    values.put(MediaStore.MediaColumns.MIME_TYPE, mimeType);
                    values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    Uri uri = activity.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (uri == null) throw new java.io.IOException("MediaStore insert failed");
                    try (OutputStream out = activity.getContentResolver().openOutputStream(uri)) {
                        if (out == null) throw new java.io.IOException("openOutputStream failed");
                        out.write(bytes);
                    }
                } else {
                    File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                    if (!dir.exists()) dir.mkdirs();
                    File file = new File(dir, filename);
                    try (FileOutputStream out = new FileOutputStream(file)) {
                        out.write(bytes);
                    }
                }
                final String msg = "Téléchargé dans \"Téléchargements\" : " + filename;
                activity.runOnUiThread(() -> Toast.makeText(activity, msg, Toast.LENGTH_LONG).show());
            } catch (Exception e) {
                activity.runOnUiThread(() ->
                    Toast.makeText(activity, "Échec du téléchargement.", Toast.LENGTH_LONG).show());
            }
        }
    }

    /* Dictée (SpeechRecognizer) + lecture (TextToSpeech) pour l'Assistant IA. Les méthodes
       @JavascriptInterface sont appelées depuis le thread JS de la WebView (pas le thread UI) :
       toute opération sur SpeechRecognizer/TextToSpeech doit donc être postée sur le thread UI.
       Les résultats reviennent au JS via evaluateJavascript() vers des callbacks globaux
       définis côté JS (window.__nativeSpeechResult/__nativeSpeechEnd/__nativeSpeechError/
       __nativeSpeechTtsEnd, voir static/js/ia.js). */
    public static class NativeSpeechBridge {
        private final Activity activity;
        private final WebView webView;
        private SpeechRecognizer recognizer;
        private TextToSpeech tts;
        private boolean ttsReady = false;

        NativeSpeechBridge(Activity activity, WebView webView) {
            this.activity = activity;
            this.webView = webView;
            this.tts = new TextToSpeech(activity, status -> ttsReady = (status == TextToSpeech.SUCCESS));
        }

        private void callJs(String fn, String arg) {
            // JSONObject.quote() échappe correctement la chaîne pour l'injecter en littéral JS.
            final String js = "javascript:(function(){if(window." + fn + ")window." + fn + "("
                + (arg == null ? "" : JSONObject.quote(arg)) + ");})();";
            activity.runOnUiThread(() -> webView.evaluateJavascript(js, null));
        }

        @JavascriptInterface
        public boolean isAvailable() {
            return SpeechRecognizer.isRecognitionAvailable(activity);
        }

        @JavascriptInterface
        public void startListening(String lang) {
            activity.runOnUiThread(() -> {
                if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    callJs("__nativeSpeechError", "permission");
                    return;
                }
                if (recognizer != null) recognizer.destroy();
                recognizer = SpeechRecognizer.createSpeechRecognizer(activity);
                recognizer.setRecognitionListener(new RecognitionListener() {
                    @Override public void onResults(Bundle results) {
                        ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                        if (matches != null && !matches.isEmpty()) callJs("__nativeSpeechResult", matches.get(0));
                        else callJs("__nativeSpeechEnd", null);
                    }
                    @Override public void onError(int error) { callJs("__nativeSpeechError", String.valueOf(error)); }
                    @Override public void onEndOfSpeech() { callJs("__nativeSpeechEnd", null); }
                    @Override public void onReadyForSpeech(Bundle params) {}
                    @Override public void onBeginningOfSpeech() {}
                    // Amplitude vocale en direct (dB, très bruyant ~10, silence ~-2) : fait
                    // « respirer » les barres de l'indicateur d'écoute (ia.js) avec la vraie
                    // voix de l'utilisateur, comme l'animation d'écoute de Gemini.
                    @Override public void onRmsChanged(float rmsdB) { callJs("__nativeSpeechRms", String.valueOf(rmsdB)); }
                    @Override public void onBufferReceived(byte[] buffer) {}
                    @Override public void onPartialResults(Bundle partialResults) {}
                    @Override public void onEvent(int eventType, Bundle params) {}
                });
                Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang);
                intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
                recognizer.startListening(intent);
            });
        }

        @JavascriptInterface
        public void stopListening() {
            activity.runOnUiThread(() -> { if (recognizer != null) recognizer.stopListening(); });
        }

        @JavascriptInterface
        public void speak(String text, String lang) {
            activity.runOnUiThread(() -> {
                if (!ttsReady || text == null || text.isEmpty()) return;
                Locale locale = (lang != null && lang.startsWith("en")) ? Locale.US : Locale.FRANCE;
                tts.setLanguage(locale);
                // Le moteur Google TTS embarque parfois plusieurs voix par langue. On ne force
                // une voix de remplacement que si elle correspond EXACTEMENT à la locale visée
                // (même pays, pas seulement même langue — une voix "fr-CA"/"fr-BE" sonnerait
                // tout aussi « pas française »), et jamais une voix nécessitant le réseau
                // (latence). Sinon on laisse tts.setLanguage() ci-dessus faire son choix par
                // défaut, plutôt que de risquer d'imposer une voix mal assortie.
                Voice meilleure = null;
                if (tts.getVoices() != null) {
                    for (Voice v : tts.getVoices()) {
                        if (v.isNetworkConnectionRequired()) continue;
                        if (!locale.equals(v.getLocale())) continue;
                        if (meilleure == null || v.getQuality() > meilleure.getQuality()) meilleure = v;
                    }
                }
                if (meilleure != null) tts.setVoice(meilleure);
                // 0.94 sonnait traînant ; 1.05 (un peu plus rapide que la vitesse "neutre"
                // 1.0) donne un débit plus vif, plus proche d'une vraie conversation.
                tts.setSpeechRate(1.05f);
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String utteranceId) {}
                    @Override public void onDone(String utteranceId) { callJs("__nativeSpeechTtsEnd", null); }
                    @Override public void onError(String utteranceId) { callJs("__nativeSpeechTtsEnd", null); }
                });
                tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "aoceda-ia-tts");
            });
        }

        @JavascriptInterface
        public void stopSpeaking() {
            activity.runOnUiThread(() -> { if (tts != null) tts.stop(); });
        }

        /* Dictée DIOULA : contrairement à startListening() ci-dessus (qui utilise le
           moteur SpeechRecognizer d'Android — lequel ne comprend pas le dioula),
           ici on enregistre l'AUDIO BRUT dans un fichier et on le renvoie encodé en
           base64 au JS (voir window.__nativeAudioRecorded, static/js/ia.js), qui
           l'envoie tel quel au serveur pour toute la compréhension + réponse. */
        private MediaRecorder recorder;
        private String cheminEnregistrement;

        @JavascriptInterface
        public void startRecordingRaw() {
            activity.runOnUiThread(() -> {
                if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    callJs("__nativeAudioError", "permission");
                    return;
                }
                try {
                    cheminEnregistrement = activity.getCacheDir().getAbsolutePath() + "/dictee_dioula.m4a";
                    recorder = new MediaRecorder();
                    recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
                    recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
                    recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
                    recorder.setAudioSamplingRate(16000);
                    recorder.setOutputFile(cheminEnregistrement);
                    recorder.prepare();
                    recorder.start();
                } catch (Exception e) {
                    recorder = null;
                    callJs("__nativeAudioError", e.getMessage());
                }
            });
        }

        @JavascriptInterface
        public void stopRecordingRaw() {
            activity.runOnUiThread(() -> {
                if (recorder == null) {
                    callJs("__nativeAudioError", "not_recording");
                    return;
                }
                try {
                    recorder.stop();
                    recorder.release();
                    byte[] octets;
                    try (java.io.FileInputStream fis = new java.io.FileInputStream(cheminEnregistrement)) {
                        octets = new byte[fis.available()];
                        int lu = fis.read(octets);
                        if (lu <= 0) throw new java.io.IOException("Fichier audio vide");
                    }
                    callJs("__nativeAudioRecorded", Base64.encodeToString(octets, Base64.NO_WRAP));
                } catch (Exception e) {
                    callJs("__nativeAudioError", e.getMessage());
                } finally {
                    recorder = null;
                }
            });
        }
    }
}
