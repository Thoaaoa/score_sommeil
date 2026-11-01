import Toybox.Lang;
using Toybox.WatchUi;
using Toybox.Graphics;
using Toybox.Communications;
using Toybox.Application.Storage;
using Toybox.PersistedContent;

// >>> A MODIFIER : l'URL de TON fichier score.json publie par sleep_score.py <<<
// (GitHub Pages sert le bon Content-Type application/json, indispensable ici)
const SCORE_URL = "https://thoaaoa.github.io/score_sommeil/score.json";

class SommeilView extends WatchUi.View {

    var _score as Number? = null;
    var _date as String = "";
    var _qualite as String = "";
    var _etat as String = "Chargement...";

    function initialize() {
        View.initialize();
        // Affiche le dernier score connu meme sans telephone a portee
        var s = Storage.getValue("dernier");
        if (s instanceof Dictionary) {
            _score = s.get("score") as Number?;
            _date = s.get("date") as String?;
            _qualite = s.get("qualite") as String?;
            _etat = "";
        }
    }

    // Appele quand le widget devient visible -> on rafraichit
    function onShow() as Void {
        Communications.makeWebRequest(
            SCORE_URL,
            null,
            {
                :method => Communications.HTTP_REQUEST_METHOD_GET,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            method(:onReponse)
        );
    }

    function onReponse(
        responseCode as Number,
        data as Dictionary or String or PersistedContent.Iterator or Null
    ) as Void {
        if (responseCode == 200 && data instanceof Dictionary && data.get("score") != null) {
            _score = data.get("score") as Number?;
            _date = data.get("date") as String?;
            _qualite = data.get("qualite") as String?;
            _etat = "";
            Storage.setValue("dernier", {
                "score" => _score,
                "date" => _date,
                "qualite" => _qualite
            });
        } else if (_score == null) {
            // code negatif = pas de reseau / telephone non connecte
            _etat = (responseCode < 0) ? "Tel. non connecte" : "Erreur " + responseCode;
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();
        var cx = dc.getWidth() / 2;
        var cy = dc.getHeight() / 2;

        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, 18, Graphics.FONT_SMALL, "Sommeil",
                    Graphics.TEXT_JUSTIFY_CENTER);

        if (_score != null) {
            // Couleur selon le score (ecran MIP 64 couleurs)
            if (_score >= 80) {
                dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
            } else if (_score >= 60) {
                dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
            } else {
                dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            }
            dc.drawText(cx, cy - 34, Graphics.FONT_NUMBER_HOT,
                        _score.toString(), Graphics.TEXT_JUSTIFY_CENTER);
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, cy + 28, Graphics.FONT_TINY, _qualite,
                        Graphics.TEXT_JUSTIFY_CENTER);
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, cy + 52, Graphics.FONT_XTINY, _date,
                        Graphics.TEXT_JUSTIFY_CENTER);
        } else {
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, cy, Graphics.FONT_SMALL, _etat,
                        Graphics.TEXT_JUSTIFY_CENTER);
        }
    }
}
