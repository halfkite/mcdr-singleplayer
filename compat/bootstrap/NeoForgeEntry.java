package io.github.mcdrsingleplayer.bootstrap;

import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;

@Mod(value = "mcdr_singleplayer", dist = Dist.CLIENT)
public final class NeoForgeEntry {
    public NeoForgeEntry() {
        try {
            var type = Class.forName(VersionSelector.implementation() + ".SingleplayerBridge");
            type.getMethod("onInitialize").invoke(type.getDeclaredConstructor().newInstance());
        } catch (ReflectiveOperationException exception) { throw new IllegalStateException("MCDR version adapter failed", exception); }
    }
}
