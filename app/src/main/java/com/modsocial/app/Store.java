package com.modsocial.app;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.*;
import java.util.UUID;

/** Device-local demo state. Remote accounts never read or write this dataset. */
final class Store {
    private final SharedPreferences prefs;
    Store(Context context) { prefs=context.getSharedPreferences("mod_demo_v1",Context.MODE_PRIVATE); }
    JSONObject load() throws JSONException {
        String saved=prefs.getString("state",null);
        if(saved!=null) return new JSONObject(saved);
        JSONObject state=new JSONObject();
        state.put("me", user("me","Engin","Mersin"));
        JSONArray users=new JSONArray();
        users.put(user("deniz","Deniz Yılmaz","Mersin"));
        users.put(user("mert","Mert Kaya","Mersin"));
        users.put(user("ece","Ece Aydın","Mersin"));
        users.put(user("selin","Selin Demir","Mersin"));
        state.put("users",users);state.put("following",new JSONArray().put("deniz").put("mert"));
        state.put("joined",new JSONArray());
        long now=System.currentTimeMillis();
        JSONArray plans=new JSONArray();
        String[] ids={"deniz","mert","ece","selin"};
        String[] titles={"Bir kahve, bolca sohbet. Kim geliyor?","Sahilde gün batımına doğru yürüyelim.","Yeni şarkılar keşfedelim. Önerisi olan?","Akşam ekibi toplanıyor. Bir kişilik yer var!"};
        String[] types={"coffee","walk","music","game"};
        for(int i=0;i<4;i++) plans.put(new JSONObject().put("id","sample-"+i).put("user_id",ids[i]).put("title",titles[i]).put("type",types[i]).put("place",i<2?"Mersin sahili":"Çevrimiçi").put("starts_at",now+(i+1)*3600000L).put("expires_at",now+86400000L).put("audience","public").put("count",i+1));
        state.put("plans",plans);save(state);return state;
    }
    static JSONObject user(String id,String name,String city)throws JSONException{return new JSONObject().put("id",id).put("name",name).put("city",city);}
    void save(JSONObject state){prefs.edit().putString("state",state.toString()).apply();}
    static boolean contains(JSONArray a,String id){for(int i=0;i<a.length();i++) if(id.equals(a.optString(i)))return true;return false;}
    static JSONArray toggled(JSONArray a,String id){JSONArray b=new JSONArray();boolean found=false;for(int i=0;i<a.length();i++){String s=a.optString(i);if(s.equals(id))found=true;else b.put(s);}if(!found)b.put(id);return b;}
    static JSONObject makePlan(String owner,String title,String type,String place,long starts,String audience)throws JSONException{
        long expiry=Math.min(System.currentTimeMillis()+86400000L,starts+2*3600000L);
        return new JSONObject().put("id",UUID.randomUUID().toString()).put("user_id",owner).put("title",title).put("type",type).put("place",place).put("starts_at",starts).put("expires_at",expiry).put("audience",audience).put("count",0);
    }
}
